"""`CorpusStore` over an ordinary local directory.

The development and test backend, and — per the parked-filesystem option in the
MVP plan — the shape a future `PosixStore` over BTRFS/ZFS would take.
"""

from __future__ import annotations

from pathlib import Path

from src.store.base import CorpusStore, ObjectStat


class LocalFsStore(CorpusStore):
    """Keys become paths under `root`. Directories are created as needed."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

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
