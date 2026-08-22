"""Rendering a change page — two surfaces over one record, neither reading git.

Implements `context-v/specs/Corpus-Change-Feed.md`. Adding an email digest or a
web view later means a third renderer, not a second reader.

Two rules, and the first is the whole point of the feature:

1. **Never invent a reason.** A change with no usable sentence renders with its
   counts and no reason line. No diff summary, no model call, no guess. An absent
   reason renders as absent, which is honest and is the only thing that creates
   pressure to write a real one (`FEED-07`). This is the corpus-boundary
   discipline — *no guesswork on factual claims* — applied to our own output.
2. **Never truncate silently.** A capped path list says how many it dropped; a
   capped page says it was capped (`FEED-09`, `FEED-13`).
"""

from __future__ import annotations

import json
from datetime import UTC

from src.feed.change import Change, ChangePage

# How many paths a prose render shows per change before summarising. A triage
# commit can touch 300 files; a client does not want the list, but they must be
# told the list was shortened.
DEFAULT_MAX_PATHS = 5

# Subjects that carry no reason a client could use. Kept deliberately tiny: the
# job is to catch the placeholder, not to judge someone's prose.
_EMPTY_SENTENCES = {"", "wip", "update", "updates", "fix", "fixes", "changes"}


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def has_reason(change: Change) -> bool:
    """Whether this change carries a sentence worth showing a client."""
    return change.sentence.strip().lower().rstrip(".") not in _EMPTY_SENTENCES


def to_json(page: ChangePage) -> str:
    """The stable machine shape. What a web view or a digest consumes."""
    return json.dumps(
        {
            "truncated": page.truncated,
            "count": len(page.changes),
            "changes": [
                {
                    "id": c.id,
                    "when": c.when.astimezone(UTC).isoformat(),
                    "who": c.who,
                    "subject": c.subject,
                    "verb": c.verb,
                    "scope": c.scope,
                    "sentence": c.sentence,
                    "added": c.added,
                    "changed": c.changed,
                    "removed": c.removed,
                    "renamed": [{"old": r.old, "new": r.new} for r in c.renamed],
                    "counts": {
                        "added": c.n_added,
                        "changed": c.n_changed,
                        "removed": c.n_removed,
                        "renamed": c.n_renamed,
                    },
                    "bytes": c.bytes_total,
                }
                for c in page.changes
            ],
        },
        indent=2,
    )


def _counts_line(change: Change) -> str:
    bits = []
    if change.n_added:
        bits.append(f"{change.n_added} added")
    if change.n_changed:
        bits.append(f"{change.n_changed} updated")
    if change.n_removed:
        bits.append(f"{change.n_removed} removed")
    if change.n_renamed:
        bits.append(f"{change.n_renamed} moved")
    if not bits:
        return "no files touched"
    line = ", ".join(bits)
    if change.bytes_total:
        line += f" · {_human_bytes(change.bytes_total)}"
    return line


def render_prose(page: ChangePage, max_paths: int = DEFAULT_MAX_PATHS) -> str:
    """The human surface — what a client reads.

    Deliberately plain text rather than `rich` markup so it is testable, and so
    the same string can go into an email, a web page, or a terminal.
    """
    if not page.changes:
        return "No changes recorded for this corpus yet."

    out: list[str] = []
    for change in page.changes:
        stamp = change.when.astimezone().strftime("%Y-%m-%d")
        out.append(f"{stamp} · {change.who}")

        # Rule 1. No sentence means no reason line — not a generated one.
        if has_reason(change):
            out.append(f"  {change.sentence}")

        out.append(f"  {_counts_line(change)}")

        shown = change.paths[:max_paths]
        for path in shown:
            out.append(f"    {path}")
        hidden = change.n_paths - len(shown)
        if hidden > 0:
            out.append(f"    +{hidden} more")
        out.append("")

    if page.truncated:
        out.append(f"Showing the {len(page.changes)} most recent changes; there are more.")
    return "\n".join(out).rstrip() + "\n"
