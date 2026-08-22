"""The `bin/` store — one remote copy per client, one cache per machine.

Implements `context-v/specs/Binary-Ingest-And-Bin-Store.md`, Behaviours 6-9 and
the two-scopes resolution.

    remote        r2://<client-bucket>/corpora/bin/<ab>/<sha256><ext>   per client
    local cache   ~/Library/Caches/corpora/bin/<ab>/<sha256><ext>       per MACHINE

`bin/` is never in a repo. That is what keeps the corpus repo around 30 MB, and
it is why Git LFS — and therefore the jj hazard that corrupted a client repo on
2026-08-22 — goes away entirely.

Four rules:

1. **The cache is shared across every corpus; the remote is not.** The key leaks
   nothing about a machine or a person, but two wrappers naming the same hash
   reveal that two clients hold the same document. Sharing the remote would
   dissolve the bucket-per-client isolation the tenancy design makes structural.
   Duplicating a 9 MB report across two buckets costs fractions of a cent.
2. **Fetched once, used by every corpus.** Precisely *because* the remote copies
   are separate objects that happen to share a name, a cache hit for one corpus
   is a cache hit for all of them.
3. **Verification never downloads.** `CorpusStore.stat()` gives size and hash;
   comparing that to the key is the whole check. 78 binaries cost 78 `stat`
   calls and no bytes.
4. **Eviction is cache eviction, and cannot lose data.** Clearing a cache entry
   is lossless by construction — a stronger guarantee than git-annex's
   `numcopies`, needing none of its bookkeeping. Nothing here deletes a remote
   object.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from src.binary.keys import BinaryRef
from src.store.base import CorpusStore, KeyNotFound

#: Reported when a binary is referenced but not on this machine. A state, not an
#: error — the operator's call, 2026-08-22: "Fail with a clear 'not downloaded,
#: click to get'." It never raises and it never silently fetches.
NOT_DOWNLOADED = "not_downloaded"
PRESENT = "present"

#: `verify` outcomes.
OK = "ok"
MISSING = "missing"
HASH_MISMATCH = "hash_mismatch"


def default_cache_dir() -> Path:
    """Machine-level, deliberately outside any repo (rule 1)."""
    if env := os.environ.get("CORPORA_CACHE_DIR"):
        return Path(env)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "corpora"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "corpora"


@dataclass(frozen=True)
class BinaryStatus:
    state: str
    key: str
    bytes: int = 0

    @property
    def is_present(self) -> bool:
        return self.state == PRESENT


@dataclass(frozen=True)
class VerifyResult:
    key: str
    outcome: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == OK


class BinStore:
    """Content-addressed binaries over a `CorpusStore`, with a machine cache."""

    def __init__(self, remote: CorpusStore, cache_dir: Path | None = None) -> None:
        self.remote = remote
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()

    # -- cache paths ---------------------------------------------------------

    def _cached(self, key: str) -> Path:
        return self.cache_dir / key

    def is_cached(self, key: str) -> bool:
        return self._cached(key).is_file()

    # -- writing -------------------------------------------------------------

    def put(self, ref: BinaryRef, data: bytes) -> BinaryRef:
        """Store bytes at their content key, remotely and in the cache.

        Idempotent by construction (rule 6 of the spec): an object at a hash key
        is immutable, so a second `put` of the same bytes is a no-op rather than
        a rewrite.
        """
        if not self.remote.exists(ref.key):
            self.remote.write(ref.key, data)
        self._write_cache(ref.key, data)
        return ref

    def _write_cache(self, key: str, data: bytes) -> None:
        path = self._cached(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic — a torn cache entry is a corrupt binary

    # -- reading -------------------------------------------------------------

    def status(self, ref: BinaryRef) -> BinaryStatus:
        """Present locally, or not downloaded. Never fetches (Behaviour 8)."""
        if self.is_cached(ref.key):
            return BinaryStatus(state=PRESENT, key=ref.key, bytes=ref.size)
        return BinaryStatus(state=NOT_DOWNLOADED, key=ref.key, bytes=ref.size)

    def fetch(self, ref: BinaryRef) -> bytes:
        """Cache first, remote second (rule 2). Populates the cache on a miss."""
        path = self._cached(ref.key)
        if path.is_file():
            return path.read_bytes()
        data = self.remote.read(ref.key)
        self._write_cache(ref.key, data)
        return data

    # -- checking ------------------------------------------------------------

    def verify(self, ref: BinaryRef) -> VerifyResult:
        """Confirm the remote holds these exact bytes, without reading them."""
        try:
            stat = self.remote.stat(ref.key)
        except KeyNotFound:
            return VerifyResult(key=ref.key, outcome=MISSING, detail="absent from the store")
        if stat.content_hash and stat.content_hash != ref.sha256:
            return VerifyResult(
                key=ref.key,
                outcome=HASH_MISMATCH,
                detail=f"store has {stat.content_hash[:12]}…, wrapper says {ref.sha256[:12]}…",
            )
        if stat.size != ref.size:
            return VerifyResult(
                key=ref.key,
                outcome=HASH_MISMATCH,
                detail=f"store has {stat.size} bytes, wrapper says {ref.size}",
            )
        return VerifyResult(key=ref.key, outcome=OK)

    # -- reclaiming space ----------------------------------------------------

    def evict(self, ref: BinaryRef) -> VerifyResult:
        """Drop the local copy, once the remote is confirmed to hold it.

        The confirmation is belt-and-braces: clearing a cache entry cannot lose
        data (rule 4). It is kept because the failure it guards against — a
        remote that quietly lost an object — is exactly the one you want to hear
        about at the moment you were about to rely on it.
        """
        result = self.verify(ref)
        if not result.ok:
            return result
        self._cached(ref.key).unlink(missing_ok=True)
        return result

    def cache_bytes(self) -> int:
        """What the machine-level cache currently costs on disk."""
        root = self.cache_dir
        if not root.is_dir():
            return 0
        return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
