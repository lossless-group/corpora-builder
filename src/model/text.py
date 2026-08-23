"""Text a reader sees, pulled out of markdown a machine fetched.

Lives in `src/model/` rather than beside the fetcher because two things need it
and they sit on opposite sides of the tree: capture stores a short excerpt on a
candidate, and the source manifest stores the longer one a listing displays.
Keeping it here means `src/index/manifest.py` can compute the same string
without importing the capture package.
"""

from __future__ import annotations

import re

_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NAV_LINE = re.compile(r"^\s*(\*|\-|#{1,6}\s|!\[|\[)")

#: The keys Jina puts above the page itself. A body captured before
#: `parse_jina_preamble` existed still carries them, and `Title: <the title>` is
#: long enough to look like prose — so the excerpt became the title, printed a
#: second time directly underneath itself. Seen across reach-edu.
#:
#: An explicit set rather than the `Key: value` shape, because real prose does
#: that too: "Education matters: here is why" is a sentence, not a preamble.
_PREAMBLE_KEYS = frozenset(
    {"title", "url source", "published time", "markdown content", "warning", "images", "links"}
)


def _is_preamble(line: str) -> bool:
    head, sep, _ = line.partition(":")
    return bool(sep) and head.strip().lower() in _PREAMBLE_KEYS


def prose_excerpt(body: str, limit: int) -> str:
    """The first real sentence or two, skipping navigation chrome.

    A page's markdown opens with skip-links, a logo, and a nav list. Storing
    that as the excerpt makes triage useless — the analyst sees "Skip to main
    content" for every source and stops reading excerpts entirely.

    It also skips a fetcher's own preamble. **An excerpt that repeats the title
    is worse than no excerpt** — it fills the line where the answer to "what is
    this" belongs with the answer already given directly above it.
    """
    for raw in body.splitlines():
        line = raw.strip()
        if not line or _NAV_LINE.match(line) or _is_preamble(line):
            continue
        cleaned = " ".join(_MD_LINK.sub(r"\1", line).split())
        if len(cleaned) < 40:  # a stray word or a caption, not prose
            continue
        return cleaned[:limit] + ("…" if len(cleaned) > limit else "")
    return ""
