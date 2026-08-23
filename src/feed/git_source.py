"""Git as a `ChangeSource` — the first implementation, and today the only one.

Implements `context-v/specs/Corpus-Change-Feed.md`. Reads with `git log --raw`,
which is plumbing-stable output rather than anything meant for humans, so the
parse does not break when porcelain formatting changes.

Three rules, each of which cost something to learn:

1. **`--raw`, not `--name-status`.** `--raw` carries the blob SHAs, which is the
   only way to get real byte sizes without walking the tree. It also carries the
   status letter, so nothing is lost by choosing it.
2. **`-M` or renames are lies.** Without rename detection a moved file reports as
   a delete plus an add, and the feed tells a client we removed something we did
   not (`FEED-11`).
3. **Read-only, always.** `git log` and `git cat-file` only. Nothing here writes
   a ref, an object, or a file (`FEED-15`). This module is safe to point at a
   client's repository.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from src.feed.change import Change, ChangePage, ChangeSource, Rename

# ASCII record/unit separators. Chosen over anything printable because a commit
# subject may contain any printable character, and a delimiter a human might
# type is a delimiter that will eventually appear in real data.
_RS = "\x1e"
_US = "\x1f"

_FORMAT = f"{_RS}%H{_US}%aI{_US}%an{_US}%s"


class GitRepoError(RuntimeError):
    """The path is not a git repository, or git refused the request."""


class GitChangeSource(ChangeSource):
    """Changes read from a git repository's history."""

    def __init__(self, repo: str | Path) -> None:
        self.repo = Path(repo).resolve()
        if not self.repo.is_dir():
            # Otherwise subprocess raises FileNotFoundError on cwd= and the
            # sidecar turns a bad path into a 500 instead of a 400.
            raise GitRepoError(f"no such directory: {self.repo}")
        if not (self.repo / ".git").exists() and not self._is_worktree():
            raise GitRepoError(f"not a git repository: {self.repo}")

    # -- plumbing -------------------------------------------------------------

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitRepoError(result.stderr.strip() or f"git {' '.join(args)} failed")
        return result.stdout

    def _is_worktree(self) -> bool:
        try:
            self._git("rev-parse", "--git-dir")
            return True
        except GitRepoError:
            return False

    def _blob_sizes(self, shas: set[str]) -> dict[str, int]:
        """Size in bytes for each blob, in one batched call.

        Per-blob `cat-file -s` would be one subprocess per file; over a corpus
        with hundreds of touched paths that dominates the run.
        """
        real = {s for s in shas if s and set(s) != {"0"}}
        if not real:
            return {}
        result = subprocess.run(
            ["git", "cat-file", "--batch-check=%(objectname) %(objectsize)"],
            cwd=self.repo,
            input="\n".join(sorted(real)),
            capture_output=True,
            text=True,
        )
        sizes: dict[str, int] = {}
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                sizes[parts[0]] = int(parts[1])
        return sizes

    # -- the interface --------------------------------------------------------

    def changes(self, prefix: str = "", limit: int = 20) -> ChangePage:
        # `--no-abbrev` matters: without it `--raw` prints 7-char SHAs, and the
        # sizes dict comes back keyed by full names, so every lookup misses and
        # every change reports zero bytes.
        args = [
            "log",
            f"--format={_FORMAT}",
            "--raw",
            "--no-abbrev",
            "-M",
            f"--max-count={limit + 1}",
        ]
        if prefix:
            args += ["--", prefix]
        raw = self._git(*args)

        records = [r for r in raw.split(_RS) if r.strip()]
        truncated = len(records) > limit
        records = records[:limit]

        parsed = [self._parse_record(r, prefix) for r in records]
        # A commit can survive `git log -- <prefix>` and still contribute no
        # paths once rename pairs are filtered to the prefix. Rule: absent, not
        # empty (`FEED-03`).
        kept = [(c, s) for c, s in parsed if c is not None and c.n_paths > 0]

        sizes = self._blob_sizes({sha for _, shas in kept for sha in shas})
        out = [
            Change(
                id=c.id,
                when=c.when,
                who=c.who,
                subject=c.subject,
                added=c.added,
                changed=c.changed,
                removed=c.removed,
                renamed=c.renamed,
                bytes_total=sum(sizes.get(sha, 0) for sha in shas),
            )
            for c, shas in kept
        ]
        return ChangePage(changes=out, truncated=truncated)

    # -- parsing --------------------------------------------------------------

    def _parse_record(self, record: str, prefix: str) -> tuple[Change | None, list[str]]:
        lines = record.split("\n")
        header = lines[0].split(_US)
        if len(header) < 4:
            return None, []
        sha, iso, who, subject = header[0], header[1], header[2], header[3]

        added: list[str] = []
        changed: list[str] = []
        removed: list[str] = []
        renamed: list[Rename] = []
        shas: list[str] = []

        for line in lines[1:]:
            if not line.startswith(":"):
                continue
            meta, _, paths_part = line.partition("\t")
            fields = meta.lstrip(":").split()
            if len(fields) < 5:
                continue
            src_sha, dst_sha, status = fields[2], fields[3], fields[4]
            paths = paths_part.split("\t")
            code = status[0]

            if code in ("R", "C") and len(paths) >= 2:
                old, new = paths[0], paths[1]
                # A rename counts only if the *destination* is in scope; a file
                # moved out of the corpus reads to a client as a removal.
                if self._in(new, prefix):
                    renamed.append(Rename(old=old, new=new))
                    shas.append(dst_sha)
                elif self._in(old, prefix):
                    removed.append(old)
                    shas.append(src_sha)
                continue

            path = paths[0]
            if not self._in(path, prefix):
                continue
            if code == "A":
                added.append(path)
                shas.append(dst_sha)
            elif code == "D":
                removed.append(path)
                shas.append(src_sha)
            else:  # M, T, and anything git adds later — a change is a change
                changed.append(path)
                shas.append(dst_sha)

        change = Change(
            id=sha,
            when=datetime.fromisoformat(iso),
            who=who,
            subject=subject,
            added=sorted(added),
            changed=sorted(changed),
            removed=sorted(removed),
            renamed=sorted(renamed, key=lambda r: r.new),
        )
        return change, shas

    @staticmethod
    def _in(path: str, prefix: str) -> bool:
        if not prefix:
            return True
        clean = prefix.rstrip("/")
        return path == clean or path.startswith(clean + "/")
