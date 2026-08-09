"""Filename grammar for a source and its binary sibling.

`<YYYY-MM-DD>_<title-slug>.md`, `_<n>` on collision, and a binary sibling that
shares the stem so the two are obviously one thing in a directory listing.

The date is `fetched_at`, not `published_at` — the filename records when the
corpus acquired this, which is the question someone scanning a directory is
actually asking.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def slugify(raw: str) -> str:
    """Lowercase, collapse punctuation to single dashes, trim.

    Accents are folded rather than dropped — "Café" becomes "cafe", not "caf".
    A filename is read by humans scanning a directory, and losing a letter reads
    as corruption.
    """
    text = unicodedata.normalize("NFKD", raw or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def source_filename(
    title: str,
    fetched_date: str,
    url: str = "",
    taken: Iterable[str] = (),
    suffix: str = ".md",
) -> str:
    """Build the filename, falling back to `url` when `title` is empty.

    Falling back to the URL rather than to "untitled" is deliberate: a directory
    of `2026-06-27_untitled_3.md` is unreadable, while a slugified URL still
    tells a human what they are looking at.
    """
    stem_source = title.strip()
    if not stem_source:
        # Strip the scheme before slugifying: "https-example-org-a-b" tells a
        # human nothing they did not already assume, and costs 6 characters of
        # a name they have to scan.
        stem_source = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url.strip(), flags=re.I)
    slug = slugify(stem_source) or "untitled"
    base = f"{fetched_date}_{slug}"

    existing = set(taken)
    candidate = f"{base}{suffix}"
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}{suffix}"
        counter += 1
    return candidate
