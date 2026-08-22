"""Content addressing for binaries — the key IS the checksum.

Implements `context-v/specs/Binary-Ingest-And-Bin-Store.md`, Behaviour 1.

Two consequences follow from naming an object after its own sha256, and both are
load-bearing rather than incidental:

1. **Dedup is free.** The same report captured into two corpora produces one
   object, with no dedup logic anywhere. The 34 duplicated PDFs in reach-edu
   collapse on contact.
2. **Presence and integrity are the same question.** Verifying a binary is
   comparing the store's reported hash to the key it is filed under — which is
   why `verify` never downloads (Behaviour 7).

The two-hex fan-out matches `restic`'s `data/<ab>/<sha256>` and Kopia's layout,
and the parked HISTORY design in the MVP plan. Not a coincidence worth breaking.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

#: Everything content-addressed lives under this prefix, remote and cached alike.
BIN_PREFIX = "bin"


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_for(digest: str, ext: str = "") -> str:
    """`bin/<first-two-hex>/<sha256><ext>`.

    `ext` is carried purely so a human (or `file`) can tell what a retrieved
    object is. It never participates in addressing — two identical PDFs saved
    under different filenames are one object.
    """
    if len(digest) != 64:
        raise ValueError(f"expected a 64-char sha256, got {len(digest)}")
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"{BIN_PREFIX}/{digest[:2]}/{digest}{ext}"


def key_for_bytes(data: bytes, ext: str = "") -> str:
    return key_for(sha256_of(data), ext)


@dataclass(frozen=True)
class BinaryRef:
    """The frontmatter join — what a wrapper `.md` carries about its binary.

    Field names avoid `bytes`/`source_bytes` because a dataclass field named
    `bytes` shadows the builtin inside the class body and breaks every later
    annotation. The *frontmatter* keys keep the readable names.

    Both hashes are present on purpose (Behaviour 5). `sha256` addresses what
    you can actually fetch; `source_sha256` records what the publisher served.
    Keeping only one loses either retrievability or citability, and a corpus
    that grounds factual claims needs both.
    """

    key: str
    sha256: str
    size: int
    source_sha256: str
    source_size: int
    optimized: bool = False

    @classmethod
    def verbatim(cls, data: bytes, ext: str = "") -> BinaryRef:
        """Stored exactly as received — no optimizer ran, or it was rejected."""
        digest = sha256_of(data)
        return cls(
            key=key_for(digest, ext),
            sha256=digest,
            size=len(data),
            source_sha256=digest,
            source_size=len(data),
            optimized=False,
        )

    @classmethod
    def from_optimized(cls, source: bytes, stored: bytes, ext: str = "") -> BinaryRef:
        digest = sha256_of(stored)
        return cls(
            key=key_for(digest, ext),
            sha256=digest,
            size=len(stored),
            source_sha256=sha256_of(source),
            source_size=len(source),
            optimized=True,
        )

    def to_frontmatter(self) -> dict[str, object]:
        """The block a wrapper `.md` carries. Key order is deliberate."""
        return {
            "binary_key": self.key,
            "binary_sha256": self.sha256,
            "binary_bytes": self.size,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_size,
            "optimized": self.optimized,
        }
