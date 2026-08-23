"""`reindex` — the one expensive operation, run deliberately.

Implements the rebuild path of `context-v/specs/Search-Index.md` Behaviour 6 and
`context-v/specs/Ranked-Search.md` Behaviour 6.

Rebuilding reads every source once. That is the cost the manifest exists to stop
a *browse* from paying, so it must never happen as a side effect of one — an 845
read rebuild hiding behind an innocent page load is exactly the failure this line
of work is against. It happens here, when somebody asks for it.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.index.manifest import fingerprint, save_manifest
from src.index.search_index import BuildResult, build_search_index
from src.server.browse import build_manifest
from src.store import CorpusStore


@dataclass
class ReindexResult:
    sources: int
    fingerprint: str
    search: BuildResult


def reindex(store: CorpusStore, prefix: str = "", search: bool = True) -> ReindexResult:
    """Rebuild the manifest, then the search bundle built from it.

    `search=False` writes the manifest alone — useful when only the listing
    matters and a Node round-trip is not wanted.
    """
    manifest = build_manifest(store, prefix)
    blob = save_manifest(store, manifest)
    if search:
        result = build_search_index(store, blob)
    else:
        result = BuildResult(ok=True, skipped="not requested")
    return ReindexResult(
        sources=len(manifest.entries),
        fingerprint=fingerprint(blob),
        search=result,
    )
