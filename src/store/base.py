"""The storage seam — one interface, many substrates.

Implements `context-v/specs/Storage-Seam.md`. Everything downstream (capture,
checkpoint history, the quality scan) reads and writes through this interface
rather than through a filesystem or an S3 client, for one reason recorded in
`context-v/plans/Corpora-Builder-MVP-R2-Native-With-Checkpoint-History.md`:

    The SUBSTRATE decision put Cloudflare R2 first, and parked a snapshotting
    filesystem (BTRFS/ZFS on a VM) with an explicit trigger to re-open at
    Phase 7. That deferral is only cheap if a `PosixStore` is a later
    implementation rather than a migration. This interface is what makes
    being wrong about R2 cost ~250 lines instead of a rewrite.

Three rules, each load-bearing:

1. **Keys are strings, not paths.** `/`-separated, no leading slash. An object
   store has no directories; the interface must not pretend otherwise, or
   `PosixStore` becomes the shape everything else is bent toward.
2. **A missing key raises.** `read` never returns empty bytes for something that
   is not there. A silent empty read is how a corrupted corpus looks healthy —
   and this corpus is grounding for client deliverables.
3. **Bytes are bytes.** Anything that round-trips on one backend round-trips on
   all of them, including non-UTF-8 binary. PDFs ride alongside their markdown
   as first-class citable artifacts, so this is not hypothetical.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class KeyNotFound(KeyError):
    """Raised when a key does not exist in the store.

    Deliberately a subclass of `KeyError` so ordinary mapping intuitions work,
    but named so a caller can distinguish "not in the corpus" from any other
    dict lookup that happens to fail nearby.
    """


@dataclass(frozen=True)
class ObjectStat:
    """What a store can tell you about an object without reading it.

    No modification time on purpose — Phase 4's checkpoints key on content hash,
    not mtime, and a field nothing consumes is a field that drifts. Open question
    1 in the spec; add it when something actually asks.
    """

    size: int
    content_hash: str  # sha256 hex digest of the content


class CorpusStore(ABC):
    """Bytes at keys. Nothing about what the keys mean."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Return the bytes at `key`, or raise `KeyNotFound`."""

    @abstractmethod
    def write(self, key: str, data: bytes) -> None:
        """Write `data` at `key`, replacing anything already there."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Whether `key` currently holds anything."""

    @abstractmethod
    def stat(self, key: str) -> ObjectStat:
        """Return size and content hash for `key`, or raise `KeyNotFound`."""

    @abstractmethod
    def list(self, prefix: str = "") -> list[str]:
        """Return all keys under `prefix`, recursively, sorted.

        Full keys, not path segments — there is no directory listing here.
        """

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove `key`. Raises `KeyNotFound` if it was not there."""
