"""Storage implementations behind the `CorpusStore` seam."""

from __future__ import annotations

from src.store.base import CorpusStore, KeyNotFound, ObjectStat
from src.store.cached import CachedStore
from src.store.local import LocalFsStore
from src.store.r2 import R2Store

__all__ = [
    "CachedStore",
    "CorpusStore",
    "KeyNotFound",
    "LocalFsStore",
    "ObjectStat",
    "R2Store",
]
