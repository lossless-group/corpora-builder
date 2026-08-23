"""Filling in `normalized_url` on sources that predate it.

Identity is the blocker for three separate pieces of work — the multibox, the
gatedbox sweep, and telling one source apart from another across organizations —
and it is available today for nothing. Measured across reach-edu on 2026-08-23:

| | |
|---|---|
| filed sources | 737 |
| carry `url:` | **737 — every one** |
| carry `normalized_url:` | 226 |
| derivable from `url`, no network | **511** |
| distinct identities afterwards | 637 |

The alternatives were worse and the data says so: basenames collide 36 times and
the collisions are not benign — `2026-06-10_just-a-moment.md` appears in four
funder folders and those are four DIFFERENT blocked fetches sharing Cloudflare's
title — and `source_uuid` covers only 241 of 737.

**This edits text, it does not re-render.** `SourceFile.parse` → set → `render`
would round-trip 511 files in a client's corpus through `FIELD_ORDER`, reordering
keys and reflowing values that nothing asked to change. A one-line insertion
leaves every other byte alone, which is the difference between a diff somebody
can read and one they have to trust. `BACKFILL-03` asserts it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.model.source import FIELD_ALIASES
from src.model.urls import normalize_url

#: Every key that means "the URL", canonical first.
#:
#: **Driven off `FIELD_ALIASES` rather than hardcoded**, because a literal
#: `^url:` misses `exact_url:` — and 589 of reach-edu's 832 sources use exactly
#: that Generation-A key. A dry run reported "590 no url" against a corpus where
#: every source has one, which is how this was caught: by running it, not by a
#: fixture.
URL_KEYS: tuple[str, ...] = ("url",) + tuple(
    key for key, canonical in FIELD_ALIASES.items() if canonical == "url"
)

#: Anchored to the line start and to an exact key, so neither a `url:` inside a
#: body nor a neighbouring `fulltext_url:` is ever mistaken for the field.
_URL_LINE = re.compile(
    r"^(" + "|".join(re.escape(k) for k in URL_KEYS) + r'):[ \t]*"?([^"\n]+)"?[ \t]*$',
    re.MULTILINE,
)
_HAS_NORMALIZED = re.compile(r"^normalized_url:", re.MULTILINE)
_FENCE = "---"


@dataclass
class Backfill:
    """What a single file needs, and why it was skipped when it was."""

    key: str
    url: str = ""
    normalized: str = ""
    #: Empty when this file would be rewritten. Otherwise the reason it is not.
    skipped: str = ""

    @property
    def writes(self) -> bool:
        return not self.skipped


@dataclass
class Plan:
    """Every file considered. A dry run and a real run produce the same plan."""

    entries: list[Backfill] = field(default_factory=list)

    @property
    def writes(self) -> list[Backfill]:
        return [e for e in self.entries if e.writes]

    def reasons(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.entries:
            if e.skipped:
                out[e.skipped] = out.get(e.skipped, 0) + 1
        return out


def _frontmatter_span(text: str) -> tuple[int, int] | None:
    """`(start, end)` of the frontmatter block's interior, or None.

    A source with no frontmatter is not a source this touches. Neither is one
    whose fence never closes — that is the stranded-content case, and a damaged
    file is not something a backfill should be the first to write to.
    """
    if not text.startswith(_FENCE):
        return None
    close = text.find(f"\n{_FENCE}", len(_FENCE))
    if close == -1:
        return None
    return len(_FENCE), close + 1


def _url_match(head: str) -> re.Match[str] | None:
    """The line carrying the URL, canonical key winning over an alias.

    A file carrying both `url` and `exact_url` is mid-migration, and the parser's
    rule is that the canonical key wins. This follows it rather than taking
    whichever happens to appear first.
    """
    matches = list(_URL_LINE.finditer(head))
    if not matches:
        return None
    for m in matches:
        if m.group(1) == "url":
            return m
    return matches[0]


def plan_one(key: str, text: str) -> Backfill:
    """What this file needs. Pure — no store, no I/O."""
    span = _frontmatter_span(text)
    if span is None:
        return Backfill(key, skipped="no frontmatter")

    head = text[span[0] : span[1]]
    if _HAS_NORMALIZED.search(head):
        return Backfill(key, skipped="already has one")

    match = _url_match(head)
    if match is None:
        return Backfill(key, skipped="no url")

    url = match.group(2).strip()
    normalized = normalize_url(url)
    if not normalized:
        return Backfill(key, url=url, skipped="url does not normalise")
    return Backfill(key, url=url, normalized=normalized)


def apply_one(text: str, entry: Backfill) -> str:
    """Insert `normalized_url` directly beneath `url:`, changing nothing else.

    Placed under whichever URL key the file actually uses, because that is where
    `FIELD_ORDER` puts it and a later re-render should be a no-op rather than a
    move. **The original key is never migrated** — `SOURCE-12`: reading a corpus
    never silently changes its schema, so an `exact_url:` file keeps saying
    `exact_url:`.
    """
    span = _frontmatter_span(text)
    assert span is not None, "plan_one already refused a file with no frontmatter"
    head = text[span[0] : span[1]]
    match = _url_match(head)
    assert match is not None, "plan_one already refused a file with no url"

    at = span[0] + match.end()
    line = f'\nnormalized_url: "{entry.normalized}"'
    return text[:at] + line + text[at:]


# ---------------------------------------------------------------------------
# over a store
# ---------------------------------------------------------------------------


def plan(store, keys: list[str]) -> Plan:  # type: ignore[no-untyped-def]
    """Read every key and decide what it needs. Writes nothing."""
    entries = []
    for key in keys:
        try:
            text = store.read(key).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — an unreadable file is skipped, not fatal
            entries.append(Backfill(key, skipped=f"unreadable: {type(exc).__name__}"))
            continue
        entries.append(plan_one(key, text))
    return Plan(entries=entries)


def apply(store, plan_: Plan) -> int:  # type: ignore[no-untyped-def]
    """Write the planned insertions. Returns how many files changed.

    Re-runnable: a file that already carries `normalized_url` is skipped by
    `plan_one`, so a second pass writes nothing.
    """
    changed = 0
    for entry in plan_.writes:
        text = store.read(entry.key).decode("utf-8", errors="replace")
        store.write(entry.key, apply_one(text, entry).encode("utf-8"))
        changed += 1
    return changed
