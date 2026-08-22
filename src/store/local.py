"""`CorpusStore` over an ordinary local directory.

The development and test backend, and — per the parked-filesystem option in the
MVP plan — the shape a future `PosixStore` over BTRFS/ZFS would take.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.store.base import CorpusStore, KeyNotFound, ObjectStat


class LocalFsStore(CorpusStore):
    """Keys become paths under `root`. Directories are created as needed."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise KeyNotFound(key)
        return path.read_bytes()

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def stat(self, key: str) -> ObjectStat:
        # Streamed rather than routed through `read`, for two reasons. Size comes
        # from the filesystem instead of from `len()` on bytes we had to
        # materialise; and `stat` stops being an object *read* at the seam level,
        # which is what lets `BinStore.verify` promise it never downloads
        # (`Corpus-Binary` Behaviour 7). `R2Store.stat` already keeps that promise
        # via HeadObject plus the sha256 it writes into object metadata; this
        # makes the local implementation honest about the same contract.
        path = self._path(key)
        if not path.is_file():
            raise KeyNotFound(key)
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return ObjectStat(size=path.stat().st_size, content_hash=digest.hexdigest())

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.is_dir():
            return []
        keys = (str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix))

    def delete(self, key: str) -> None:
        path = self._path(key)
        if not path.is_file():
            raise KeyNotFound(key)
        path.unlink()
