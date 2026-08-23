"""The derived indexes a corpus carries.

The source manifest, and the search bundle built from it.
"""

from __future__ import annotations

from src.index.manifest import (
    INDEX_PREFIX,
    MANIFEST_KEY,
    Entry,
    Manifest,
    entry_from_source,
    fingerprint,
    listing_excerpt,
    load_manifest,
    save_manifest,
)

__all__ = [
    "INDEX_PREFIX",
    "MANIFEST_KEY",
    "Entry",
    "Manifest",
    "entry_from_source",
    "fingerprint",
    "listing_excerpt",
    "load_manifest",
    "save_manifest",
]
