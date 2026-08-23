"""Building and locating the Pagefind bundle.

Implements the Python half of `context-v/specs/Ranked-Search.md`.

Three rules:

1. **Pagefind does not replace the manifest.** It has no incremental add — one
   new source means rebuilding the whole index — so it cannot be kept fresh on
   capture. The manifest stays the always-current answer for listing and
   filtering; this is ranking on top of it.
2. **No Node, no bundle, no failure.** `scripts/check.sh` already skips its Node
   rungs rather than failing when Node is absent, so the Python side stays
   runnable on a machine that has never built the frontend. Reindexing does the
   same, and says so.
3. **Only `index/` is written.** Building a search index must not be able to
   modify a source. Asserted by `SEARCH-08`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.index.manifest import INDEX_PREFIX, fingerprint
from src.store import CorpusStore, KeyNotFound

#: Where the bundle lands in the corpus. Served by the sidecar at `/pagefind/*`,
#: which is what keeps a private bucket private while still letting the webview
#: load a WebAssembly module out of it.
BUNDLE_PREFIX = f"{INDEX_PREFIX}pagefind/"

#: The fingerprint of the manifest this bundle was built from. Compared against
#: the live manifest to decide whether the ranking is stale — a content hash
#: rather than a clock, so reindexing an unchanged corpus does not make every
#: bundle look out of date.
BUNDLE_FINGERPRINT_KEY = f"{INDEX_PREFIX}pagefind.sha256"

#: Bundle directories whose filenames are hashes of their own contents. A key
#: that is already present under one of these is already correct, so a rebuild
#: can skip it. Everything at the bundle root — the runtime, the stylesheets,
#: the entry manifest — is NOT addressed this way and is always rewritten.
CONTENT_ADDRESSED = ("fragment/", "index/", "filter/")

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "app" / "scripts" / "build-search-index.mjs"


@dataclass
class BuildResult:
    """What a bundle build did, including when it deliberately did nothing."""

    ok: bool
    #: Set when the build was skipped rather than run. A skip is a success with
    #: an explanation, never a silent no-op.
    skipped: str = ""
    #: Set when the build ran and failed.
    error: str = ""
    records: int = 0
    files: int = 0
    #: How many of `files` actually had to be sent. The rest were already
    #: in the store under a content-addressed name, so they were already
    #: right — which is what keeps a rebuild from costing 1,700 operations
    #: against a client's bucket.
    written: int = 0
    #: Exactly which keys were sent. Carried because the count alone cannot
    #: answer the question that matters — *did the bulk move?* Pagefind's
    #: index chunks are not byte-identical across runs, so a rebuild resends
    #: one or two of them at random; the 845 fragments must never move.
    written_keys: list[str] = field(default_factory=list)


def _content_type(name: str) -> str:
    """The type each bundle file's runtime actually requires.

    The WebAssembly module is the one that matters: browsers refuse to
    stream-compile anything not served as `application/wasm`, and Pagefind's
    fallback path is slower and quieter about it.
    """
    if name.endswith(".pagefind") or name.endswith(".wasm"):
        return "application/wasm"
    if name.endswith(".js"):
        return "text/javascript"
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".css"):
        return "text/css"
    return "application/octet-stream"


def bundle_key(rel: str) -> str:
    """The corpus key for a path within the bundle."""
    return f"{BUNDLE_PREFIX}{rel}"


def bundle_content_type(rel: str) -> str:
    return _content_type(rel)


def bundle_cache_control(rel: str) -> str:
    """How long a bundle file may be reused.

    Fragments, index shards and filter shards are named by a hash of their own
    contents — a given name can never mean different bytes — so they are
    immutable and the browser should never ask twice. That matters because
    drawing a page of results fetches one fragment per row, and a second search
    touching the same top results would otherwise pay for them all over again.

    Everything at the bundle root is rewritten on every build, so it is not.
    """
    if rel.startswith(CONTENT_ADDRESSED) or rel.endswith(".pf_meta"):
        return "public, max-age=31536000, immutable"
    return "no-cache"


def bundle_fingerprint(store: CorpusStore) -> str:
    """The manifest fingerprint the current bundle was built from, or empty."""
    try:
        return store.read(BUNDLE_FINGERPRINT_KEY).decode("utf-8").strip()
    except KeyNotFound:
        return ""


def build_search_index(store: CorpusStore, manifest_blob: bytes) -> BuildResult:
    """Build a Pagefind bundle from `manifest_blob` and write it into the store.

    The manifest is handed over as a file on disk rather than as a store the
    Node process could reach. That is what keeps the storage seam intact: a Node
    script that learned to talk to R2 would be a second, untested implementation
    of `CorpusStore`.
    """
    node = shutil.which("node")
    if node is None:
        return BuildResult(ok=True, skipped="node is not on PATH")
    if not BUILDER.is_file():
        return BuildResult(ok=True, skipped=f"builder not found at {BUILDER}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        manifest_path = work / "sources.jsonl"
        manifest_path.write_bytes(manifest_blob)
        out = work / "pagefind"

        proc = subprocess.run(
            [node, str(BUILDER), "--manifest", str(manifest_path), "--out", str(out)],
            # Run from `app/` so `import 'pagefind'` resolves against the
            # frontend's own node_modules rather than wherever the caller stood.
            cwd=str(BUILDER.parent.parent),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            return BuildResult(ok=False, error=detail[-1] if detail else "pagefind build failed")

        try:
            records = int(json.loads(proc.stdout.strip().splitlines()[-1])["records"])
        except (ValueError, KeyError, IndexError):
            records = 0

        files = list(sorted(f for f in out.rglob("*") if f.is_file()))
        existing = set(store.list(BUNDLE_PREFIX))
        produced: set[str] = set()
        sent: list[str] = []
        written = 0

        for f in files:
            rel = f.relative_to(out).as_posix()
            key = bundle_key(rel)
            produced.add(key)
            # Measured on an 845-source corpus: the bundle is 866 objects,
            # because Pagefind writes one fragment per record. Rewriting all of
            # them on every rebuild is ~1,700 R2 operations against a client's bucket
            # for a corpus that may have gained one source.
            #
            # Everything under these three directories is named by a hash of its
            # own contents, so a key that is already there is already right.
            if key in existing and rel.startswith(CONTENT_ADDRESSED):
                continue
            store.write(key, f.read_bytes())
            written += 1
            sent.append(key)

        # Orphans still have to go. A rebuild after a deletion produces fewer
        # chunks, and anything left behind is a chunk the runtime would happily
        # fetch and read as current.
        for key in existing - produced:
            store.delete(key)

    store.write(BUNDLE_FINGERPRINT_KEY, fingerprint(manifest_blob).encode("utf-8"))
    return BuildResult(
        ok=True, records=records, files=len(files), written=written, written_keys=sent
    )
