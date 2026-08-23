"""The source manifest — what a listing needs, written down once.

Implements `context-v/specs/Search-Index.md`.

A search opens every file in the corpus: 845 round-trips and up to 5.8 seconds
against reach-edu, versus 0.48s for an unsearched page. Everything a search needs
is a small fixed set of fields per source, so writing them down turns 845 reads
into one. `Strategy-Focus.md` §4 named this fix and declined to build it; this is
it.

Four rules, each load-bearing:

1. **It stores what the FILE says, never what this machine knows.** `domain` is
   derivable from the key and `binary_state` is per-machine — both are absent on
   purpose. A stored derived value drifts; a stored per-machine value is the bug
   `BinStore`'s two-bucket test exists to catch.
2. **A file that will not parse gets an entry carrying its error.** `browse.py`
   opens by naming the ImmuneCo failure — 13 sources silently absent from a
   count. An index that quietly omits what it could not parse reproduces that
   with a speedup attached.
3. **No timestamp.** Freshness is decided per-key by the caller, not by a clock,
   and a `built_at` would make two rebuilds of an unchanged corpus differ. Where
   a fingerprint is needed it is the sha256 of these very bytes — which is what
   lets the search bundle know whether it is stale.
4. **Sorted by key, one entry per line.** Sorted so a diff shows what changed
   rather than a reshuffle, the same reasoning as `FIELD_ORDER`. Line-per-entry
   so a damaged manifest costs one source rather than the file.

This module knows nothing about rows or HTTP. The conversions live in
`src/server/browse.py`, which is what keeps the dependency pointing one way.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from src.model import SourceFile
from src.model.text import prose_excerpt
from src.store import CorpusStore, KeyNotFound

#: Everything derived rather than captured. Hidden from the listing and from the
#: corpus tree — the test is not "is this internal?" but "does this level tell
#: the reader anything?", and a cache does not.
INDEX_PREFIX = "index/"

MANIFEST_KEY = f"{INDEX_PREFIX}sources.jsonl"

#: How much body prose a listing shows when a file carries no `excerpt`. Larger
#: than the capture-time cap because a listing is a reading surface, not a stored
#: field. Lives here rather than in `browse.py` so the manifest and the direct
#: read cannot disagree about what they computed.
PREVIEW_CHARS = 240


def listing_excerpt(source: SourceFile) -> str:
    """The excerpt a listing shows for `source`.

    reach-edu's 845 files carry no `excerpt:` at all — they predate the field —
    so this falls back to the first real prose in the body, and search matches
    *that*. The manifest stores this exact string; storing anything else would
    mean the arrival of an index silently changed what search finds.
    """
    return source.excerpt or prose_excerpt(source.body, PREVIEW_CHARS)


@dataclass
class Entry:
    """One source, as a listing needs it.

    Mirrors `SourceRow` minus the two fields that must never be stored: `domain`
    (derivable from `key`) and `binary_state` (true of a machine, not of a file).
    """

    key: str
    title: str = ""
    url: str = ""
    #: Carried so capture's duplicate check can run without opening every file
    #: under the prefix, which is what it did before this existed.
    normalized_url: str = ""
    status: str = ""
    content_pulled: bool = False
    published_at: str = ""
    fetched_at: str = ""
    excerpt: str = ""
    domains: list[str] = field(default_factory=list)
    binary_key: str = ""
    binary_bytes: int = 0
    binary_optimized: bool = False
    #: Set when the file could not be parsed. Rule 2 — present, never dropped.
    error: str = ""

    def to_json(self) -> dict[str, object]:
        """Falsy fields are omitted, so a text-only source is one short line.

        Deterministic regardless: dataclass field order is insertion order, and
        the same input always omits the same keys.
        """
        return {k: v for k, v in asdict(self).items() if k == "key" or v}

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> Entry:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})  # type: ignore[arg-type]


def entry_from_source(key: str, source: SourceFile) -> Entry:
    """The entry for a source that parsed."""
    asset = source.binary_asset
    has_binary = asset is not None and bool(asset.binary_key)
    return Entry(
        key=key,
        title=source.title,
        url=source.url,
        normalized_url=source.normalized_url,
        status=source.status,
        content_pulled=source.content_pulled,
        published_at=str(source.published_at or ""),
        fetched_at=str(source.fetched_at or ""),
        excerpt=listing_excerpt(source),
        domains=list(source.domains),
        binary_key=asset.binary_key if has_binary and asset else "",
        binary_bytes=asset.working_bytes if has_binary and asset else 0,
        binary_optimized=asset.was_compressed if has_binary and asset else False,
    )


def entry_from_failure(key: str, error: str) -> Entry:
    """The entry for a file that would not parse.

    Title falls back to the filename, matching what a direct read renders, so a
    damaged file looks the same indexed or not.
    """
    return Entry(key=key, title=key.rsplit("/", 1)[-1], error=error)


@dataclass
class Manifest:
    """Every indexed source, keyed by corpus key."""

    entries: dict[str, Entry] = field(default_factory=dict)

    def keys(self) -> set[str]:
        return set(self.entries)

    def render(self) -> bytes:
        """JSONL, sorted by key. Byte-identical for identical input."""
        lines = [
            json.dumps(self.entries[k].to_json(), ensure_ascii=False, separators=(",", ":"))
            for k in sorted(self.entries)
        ]
        return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""

    @classmethod
    def parse(cls, blob: bytes) -> Manifest:
        """A damaged line costs one source, not the manifest — rule 4."""
        entries: dict[str, Entry] = {}
        for line in blob.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if not isinstance(raw, dict) or not raw.get("key"):
                continue
            entry = Entry.from_json(raw)
            entries[entry.key] = entry
        return cls(entries=entries)


def fingerprint(blob: bytes) -> str:
    """The manifest's identity, for anything built downstream of it.

    A content hash rather than a clock: rebuilding an unchanged corpus must
    produce an unchanged fingerprint, or the search bundle would look stale every
    time somebody reindexed.
    """
    return hashlib.sha256(blob).hexdigest()


def load_manifest(store: CorpusStore) -> Manifest | None:
    """The corpus's manifest, or `None` when it has never been indexed.

    `None` is a real answer and not an error: whether a corpus is indexed is an
    explicit operator decision made by running `reindex`, and an unindexed corpus
    must go on behaving exactly as it did before this module existed.
    """
    try:
        return Manifest.parse(store.read(MANIFEST_KEY))
    except KeyNotFound:
        return None


def save_manifest(store: CorpusStore, manifest: Manifest) -> bytes:
    """Write it, and hand back the bytes so a caller can fingerprint them."""
    blob = manifest.render()
    store.write(MANIFEST_KEY, blob)
    return blob
