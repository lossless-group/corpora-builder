"""A read-through cache over any other `CorpusStore`.

Why this exists at all: the PROVING-CORPUS is 517 files and 156MB, and going
R2-native means every read is a network call. A scan that does 517 round trips
is a scan nobody runs.

Correctness is cheap here because Phase 4 makes content addressing the norm —
an object named by its own sha256 can never change, so a cache keyed on it never
needs invalidating. This phase's cache is keyed on the plain key instead, so it
DOES need invalidating, and writing through the cache is the moment that
happens. A stale cache must never win: that is `STORE-13`.
"""

from __future__ import annotations

from src.store.base import CorpusStore, ObjectStat


class CachedStore(CorpusStore):
    """Wraps `backing`, serving repeat reads from memory."""

    def __init__(self, backing: CorpusStore) -> None:
        self.backing = backing
        self._cache: dict[str, bytes] = {}

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def write(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def stat(self, key: str) -> ObjectStat:
        raise NotImplementedError

    def list(self, prefix: str = "") -> list[str]:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError
