"""Domain references — the `kind:slug` chain a source names its scope with.

A **domain reference** is not a tag, and conflating them is how a scope quietly
becomes a keyword. Both fields exist on a source and they answer different
questions:

| | `domains:` | `tags:` |
|---|---|---|
| example | `strategy:workforce-development` | `Workforce-Development` |
| shape | `kind:slug`, colon-separated, lowercase | Train-Case, minor words lowercase |
| what it is | a **scope** — which corpus this belongs to | a **label** — what it is about |
| structure | cascades, below | flat |

Measured across reach-edu on 2026-08-23: 241 sources carry `domains:` (8 distinct
values, every one exactly two segments) and 191 carry `tags:` (88 distinct
values, 100% Train-Case). No domain value is Train-Case; no tag contains a colon.

**The cascade is invoked, not stored** — see
`ai-labs/context-v/specs/Flexible-Entity-Relationships-to-Mirror-Messy-IRL-Collaboration.md`.
A reference named alone is independent; naming a *shorter* chain is a different
act, and it is what reaches everything beneath. The corpus path has always
behaved this way (`_in_domain`: `d == domain or d.startswith(domain + "/")`,
which is why `funders/` is a legal filter). This gives the reference the same
cascade the path has.
"""

from __future__ import annotations

#: What separates one link of a chain from the next.
SEP = ":"


def cascade_prefixes(reference: str) -> list[str]:
    """Every chain `reference` answers to, shortest first.

    `strategy:workforce-development` → `["strategy", "strategy:workforce-development"]`

    Used where a matcher cannot run at query time and the answers have to be
    written down in advance — the search bundle's filter values being the case
    that exists. Expanding at index time is what lets an exact-match filter
    engine honour a cascade it knows nothing about.
    """
    parts = [p for p in reference.split(SEP) if p]
    return [SEP.join(parts[: i + 1]) for i in range(len(parts))]


def matches(reference: str, focus: str) -> bool:
    """Does `reference` fall under `focus`?

    **On the separator, never on the string.** `strategy` must not match
    `strategy-two:anything`, and a bare `startswith` says it does — the same trap
    `_in_domain` avoids by testing `domain + "/"`.
    """
    if not focus:
        return True
    return reference == focus or reference.startswith(focus + SEP)


def any_match(references: list[str], focus: str) -> bool:
    """Whether any of a source's references falls under `focus`."""
    return any(matches(r, focus) for r in references)
