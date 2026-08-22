"""Capture a binary: optimize once, hash what will be stored, record both.

Implements `context-v/specs/Binary-Ingest-And-Bin-Store.md`, Behaviours 2 and 5,
and the migration in Behaviour 11.

The ordering here is the whole point and is easy to get backwards:
**optimize, then hash.** The key must address what you will actually retrieve,
so the artifact is finalised before it is named. Hashing the source and then
compressing would leave a key pointing at bytes nobody has.

Provenance survives that ordering because `BinaryRef` carries both digests — the
stored one to fetch by, the source one to cite by. Drop `source_sha256` and
"here is the source" points at something we altered and cannot prove faithful.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.binary.keys import BinaryRef
from src.binary.optimize import OptimizeResult, optimize_pdf
from src.binary.store import BinStore


@dataclass(frozen=True)
class IngestResult:
    ref: BinaryRef
    optimize: OptimizeResult
    #: Where it came from, when ingest walked a tree. A migration report you
    #: cannot trace back to a file is half a report — the first real run turned
    #: up one text-loss rejection and nine that Ghostscript made larger, and
    #: "which ones" is the only useful next question.
    source_path: Path | None = None

    @property
    def saved_bytes(self) -> int:
        return self.ref.source_size - self.ref.size


def ingest_binary(
    store: BinStore,
    data: bytes,
    ext: str = ".pdf",
    *,
    optimize: bool = True,
    compress: Callable[[bytes], bytes] | None = None,
    extract_text: Callable[[bytes], str] | None = None,
    source_path: Path | None = None,
) -> IngestResult:
    """Optimize (if it is a PDF and it is safe), store by content hash, describe."""
    if optimize and ext.lower() == ".pdf":
        kwargs: dict[str, object] = {"compress": compress}
        if extract_text is not None:
            kwargs["extract_text"] = extract_text
        result = optimize_pdf(data, **kwargs)  # type: ignore[arg-type]
    else:
        result = OptimizeResult(data=data, optimized=False, reason="not_a_pdf")

    ref = (
        BinaryRef.from_optimized(source=data, stored=result.data, ext=ext)
        if result.optimized
        else BinaryRef.verbatim(data, ext=ext)
    )
    store.put(ref, result.data)
    return IngestResult(ref=ref, optimize=result, source_path=source_path)


def migrate_tree(
    store: BinStore,
    root: Path,
    suffixes: tuple[str, ...] = (".pdf", ".docx", ".pptx", ".xlsx"),
    *,
    optimize: bool = True,
) -> list[IngestResult]:
    """Hash every existing binary under `root` into `bin/`.

    **Deletes nothing.** Removing the originals is a separate, explicitly
    confirmed step per the Autonomy-Gates RED list on deleting corpus content
    (Behaviour 11). Idempotent: a second run re-derives the same keys and `put`
    skips objects the store already holds.
    """
    out: list[IngestResult] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes:
            out.append(
                ingest_binary(
                    store,
                    path.read_bytes(),
                    ext=path.suffix,
                    optimize=optimize,
                    source_path=path,
                )
            )
    return out
