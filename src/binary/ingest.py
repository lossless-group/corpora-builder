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

from src.binary.keys import BinaryRef, sha256_of
from src.binary.optimize import OptimizeResult, optimize_pdf
from src.binary.pointer import Pointer, apply_pointer, has_pointer_for
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


def _wrapper_for(path: Path) -> Path:
    """The markdown that describes this binary — same stem, `.md` suffix."""
    return path.with_suffix(".md")


def migrate_tree(
    store: BinStore,
    root: Path,
    suffixes: tuple[str, ...] = (".pdf", ".docx", ".pptx", ".xlsx"),
    *,
    optimize: bool = True,
    write_wrappers: bool = True,
) -> list[IngestResult]:
    """File every binary under `root` into `bin/` **and point its wrapper at it**.

    Three rules, each learned the hard way on 2026-08-22:

    1. **Object and pointer are one operation** (Behaviour 12). An unreferenced
       optimized object cannot be traced back to its source.
    2. **Both copies are stored** (Behaviour 14). The optimized artifact is what
       you fetch; the publisher's original stays retrievable at its own key,
       because "usually no use for it, but every once in a while there is" only
       works if it is actually there.
    3. **The wrapper is patched, not re-rendered** (`src/binary/pointer.py`).
       Re-serializing a real wrapper produced 250 discrepancies across 34 files.

    **Deletes nothing.** Skips anything already mapped, so a second run is free.
    """
    out: list[IngestResult] = []
    for path in sorted(root.rglob("*")):
        if not (path.is_file() and path.suffix.lower() in suffixes):
            continue
        data = path.read_bytes()
        source_digest = sha256_of(data)
        wrapper = _wrapper_for(path)

        if wrapper.is_file() and has_pointer_for(
            wrapper.read_text(errors="replace"), source_digest
        ):
            continue

        result = ingest_binary(store, data, ext=path.suffix, optimize=optimize, source_path=path)

        # Rule 2 — the original is retrievable at its own content key, whether or
        # not it is the working copy.
        if result.ref.optimized:
            store.put(BinaryRef.verbatim(data, ext=path.suffix), data)

        if write_wrappers and wrapper.is_file():
            patched = apply_pointer(
                wrapper.read_text(errors="replace"),
                Pointer(
                    binary_key=result.ref.key,
                    optimized=result.ref.optimized,
                    optimized_sha256=result.ref.sha256 if result.ref.optimized else "",
                    optimized_bytes=result.ref.size if result.ref.optimized else 0,
                    source_sha256=result.ref.source_sha256,
                    source_bytes=result.ref.source_size,
                ),
            )
            wrapper.write_text(patched)
        out.append(result)
    return out
