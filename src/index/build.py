"""Building the source manifest — reading a corpus once, writing down what a listing needs.

Implements the build half of `context-v/specs/Search-Index.md`.

This lived in `src/server/browse.py` until `src/index/rebuild.py` needed it, which
left the engine importing from the server — the wrong direction for a layer that
the CLI also uses. It moved here so the dependency runs one way only: the server
reads the index; the index knows nothing about the server.

Two rules:

1. **A file that will not parse still gets an entry, carrying its error.** The
   ImmuneCo failure was 13 sources silently absent from a count. `entry_for` is
   where that is made impossible.
2. **Building is deliberate.** `build_manifest` reads every source; it runs from
   `corpora reindex` or `POST /api/reindex`, never as a side effect of a browse.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.index.manifest import (
    INDEX_PREFIX,
    Entry,
    Manifest,
    entry_from_failure,
    entry_from_source,
)
from src.model import SourceFile
from src.store import CorpusStore

#: Files that describe the corpus rather than being captured material.
#: An `index.md` is a domain's statement of the case; `AGENTS.md` and `README.md`
#: are instructions. Listing them as sources renders them with no URL and
#: `status: candidate`, indistinguishable from something we found and never
#: fetched — 13 such rows in reach-edu, inflating "845 sources" by that much.
NOT_SOURCES = ("index.md", "AGENTS.md", "README.md")


def select_sources(keys: list[str]) -> list[str]:
    """The captured sources among `keys`.

    Excludes the corpus's own documentation (`NOT_SOURCES`) and everything under
    `index/`, which this tool derives rather than captures.
    """
    return [
        k
        for k in keys
        if k.endswith(".md")
        and not k.startswith(INDEX_PREFIX)
        and k.rsplit("/", 1)[-1] not in NOT_SOURCES
    ]


def source_keys(store: CorpusStore, prefix: str = "") -> list[str]:
    """Every key under `prefix` that is a captured source."""
    return select_sources(store.list(prefix))


def read_many(store: CorpusStore, keys: list[str]) -> dict[str, bytes | Exception]:
    """Read `keys` concurrently, recording failures rather than raising.

    Against R2 each GET is ~140ms of latency and almost no transfer, so fifty
    sequential reads spend seven seconds waiting rather than working. botocore
    clients are thread-safe for requests, and a LocalFsStore does not care.
    """
    blobs: dict[str, bytes | Exception] = {}
    if not keys:
        return blobs
    with ThreadPoolExecutor(max_workers=min(16, len(keys))) as pool:
        futures = {pool.submit(store.read, k): k for k in keys}
        for fut in as_completed(futures):
            key = futures[fut]
            try:
                blobs[key] = fut.result()
            except Exception as exc:  # noqa: BLE001 - recorded, not raised
                blobs[key] = exc
    return blobs


def entry_for(key: str, blob: bytes | Exception) -> Entry:
    """One key's manifest entry, whether or not it parsed."""
    try:
        if isinstance(blob, Exception):
            raise blob
        return entry_from_source(key, SourceFile.parse(blob.decode("utf-8", errors="replace")))
    except Exception as exc:  # noqa: BLE001 - a damaged file must still list
        return entry_from_failure(key, f"{type(exc).__name__}: {exc}")


def build_manifest(store: CorpusStore, prefix: str = "") -> Manifest:
    """Read the corpus once and write down what a listing needs.

    The expensive operation, run deliberately by `corpora reindex` — never as a
    side effect of browsing, which would put an 845-read rebuild behind an
    innocent page load.
    """
    keys = source_keys(store, prefix)
    blobs = read_many(store, keys)
    return Manifest(entries={k: entry_for(k, blobs.get(k, KeyError(k))) for k in keys})
