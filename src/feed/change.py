"""The change record — what a client sees, independent of what produced it.

Implements `context-v/specs/Corpus-Change-Feed.md`. Everything that renders
"what changed in this corpus and why" reads a `Change`, never a version-control
system, for one reason recorded in the spec:

    History for this corpus currently lives in git. It may later live in a Kopia
    repository, or in corpora-builder's own checkpoints. If the feed reads
    `git log` directly, answering any of those means rebuilding the surface.

This is the same seam argument `src/store/base.py` makes for storage, and the
conformance suite (`FEED-14`) is its `STORE-11`.

Four rules, each load-bearing:

1. **Counts are derived, never stored.** `n_added` and friends read the path
   lists. A separately-stored count is a number that can disagree with the thing
   it counts, and a feed whose numbers contradict its own detail is worse than
   no feed.
2. **`subject` is always retained verbatim.** The Lossless header convention
   (`verb(scope): sentence`) is parsed *in addition to*, never *instead of*, the
   raw line. A subject that does not match the convention is not an error.
3. **A rename is a rename.** Not a removal plus an addition. A client reading
   "removed the Carnegie file, added the Carnegie file" draws the wrong
   conclusion from a correct diff.
4. **`when` is timezone-aware UTC, always.** Formatting for a reader happens in
   a renderer and nowhere else — per
   `lossless-monorepo/context-v/reminders/Dates-Are-UTC-At-Rest-Viewer-Local-At-Render.md`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

# `verb(scope): sentence` — the Lossless commit-header convention. The scope is
# optional so `capture: something` parses too. Deliberately not anchored to a
# vocabulary of verbs: a new verb should parse, not fall through to "unparsed".
_HEADER = re.compile(r"^(?P<verb>[a-z][a-z0-9-]*)(?:\((?P<scope>[^)]*)\))?:\s*(?P<sentence>.+)$")


def parse_subject(subject: str) -> tuple[str | None, str | None, str]:
    """Split a commit subject into `(verb, scope, sentence)`.

    A subject that does not match the convention yields `(None, None, subject)`
    — the whole line becomes the sentence rather than being discarded. That is
    `FEED-06`, and it is why early developer-shaped history still renders.
    """
    match = _HEADER.match(subject.strip())
    if not match:
        return None, None, subject.strip()
    scope = match.group("scope")
    return match.group("verb"), (scope if scope else None), match.group("sentence").strip()


@dataclass(frozen=True)
class Rename:
    """One path that moved. Kept as a pair so a renderer can say so."""

    old: str
    new: str


@dataclass(frozen=True)
class Change:
    """One unit of work against a corpus, whatever engine recorded it."""

    id: str
    when: datetime
    who: str
    subject: str
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    renamed: list[Rename] = field(default_factory=list)
    bytes_total: int = 0

    def __post_init__(self) -> None:
        if self.when.tzinfo is None or self.when.utcoffset() != UTC.utcoffset(None):
            # Rule 4. Normalising here rather than trusting every caller is the
            # only way `FEED-08` can hold for a source we have not written yet.
            object.__setattr__(self, "when", self.when.astimezone(UTC))

    # -- the parsed header, derived rather than stored (rule 2) ---------------

    @property
    def verb(self) -> str | None:
        return parse_subject(self.subject)[0]

    @property
    def scope(self) -> str | None:
        return parse_subject(self.subject)[1]

    @property
    def sentence(self) -> str:
        return parse_subject(self.subject)[2]

    # -- counts, derived rather than stored (rule 1) --------------------------

    @property
    def n_added(self) -> int:
        return len(self.added)

    @property
    def n_changed(self) -> int:
        return len(self.changed)

    @property
    def n_removed(self) -> int:
        return len(self.removed)

    @property
    def n_renamed(self) -> int:
        return len(self.renamed)

    @property
    def n_paths(self) -> int:
        """Every path this change touched, renames counted once."""
        return self.n_added + self.n_changed + self.n_removed + self.n_renamed

    @property
    def paths(self) -> list[str]:
        """Every touched path, renames represented by their destination."""
        return [*self.added, *self.changed, *self.removed, *(r.new for r in self.renamed)]


@dataclass(frozen=True)
class ChangePage:
    """A bounded window onto a change history.

    `truncated` exists so a capped result can say so. A feed that quietly drops
    rows reads as "that is everything", which is the failure this product exists
    to prevent (`FEED-12`).
    """

    changes: list[Change]
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.changes)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.changes)


class ChangeSource(ABC):
    """Where changes come from. Git today; a Kopia repository or our own
    checkpoints later, without anything above this line noticing."""

    @abstractmethod
    def changes(self, prefix: str = "", limit: int = 20) -> ChangePage:
        """Changes touching `prefix`, newest first, at most `limit`.

        A change touching nothing under `prefix` is absent entirely — not an
        empty entry (`FEED-03`). A change touching some files under it carries
        only those paths (`FEED-04`).
        """
        raise NotImplementedError
