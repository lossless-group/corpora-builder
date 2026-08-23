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
    """The markdown that describes this binary — same stem, `.md` suffix.

    The corpus convention since capture began: `report.pdf` is described by
    `report.md` beside it. That pairing is what makes a migration able to write
    the pointer at all.
    """
    return path.with_suffix(".md")


def _already_mapped(wrapper: Path, source_sha256: str) -> bool:
    """Whether this wrapper already points at the right object (Behaviour 13).

    Cheap and deliberately textual: parsing every wrapper's YAML to answer a
    yes/no question is the difference between a migration that re-runs in a
    second and one that re-runs in three minutes.
    """
    if not wrapper.is_file():
        return False
    text = wrapper.read_text(errors="replace")
    return "binary_key:" in text and source_sha256 in text


def migrate_tree(
    store: BinStore,
    root: Path,
    suffixes: tuple[str, ...] = (".pdf", ".docx", ".pptx", ".xlsx"),
    *,
    optimize: bool = True,
    write_wrappers: bool = True,
) -> list[IngestResult]:
    """File every binary under `root` into `bin/` **and point its wrapper at it**.

    Storing the object and writing the pointer are one operation (Behaviour 12).
    An object in `bin/` that no wrapper references is garbage rather than
    progress — and because optimization changes identity as well as bytes, an
    unreferenced optimized object cannot be traced back to its source. That is
    not hypothetical: it happened on 2026-08-22, see
    `context-v/issues/Orphaned-Bin-Objects-From-A-Half-Migration.md`.

    **Deletes nothing.** Removing originals is a separate, explicitly confirmed
    step per the Autonomy-Gates RED list (Behaviour 11).

    **Skips what is already mapped** (Behaviour 13), so a second run neither
    re-optimizes nor re-uploads.
    """
    out: list[IngestResult] = []
    for path in sorted(root.rglob("*")):
        if not (path.is_file() and path.suffix.lower() in suffixes):
            continue
        data = path.read_bytes()
        wrapper = _wrapper_for(path)
        if _already_mapped(wrapper, sha256_of(data)):
            continue
        result = ingest_binary(store, data, ext=path.suffix, optimize=optimize, source_path=path)
        if write_wrappers and wrapper.is_file():
            _write_pointer(wrapper, result.ref)
        out.append(result)
    return out


def _write_pointer(wrapper: Path, ref: BinaryRef) -> None:
    """Record the pointer on an existing wrapper, preserving everything else.

    Parsed and re-rendered through `SourceFile` rather than patched textually,
    so field order and unknown keys survive — the frontmatter contract belongs
    to that model, not to this function.
    """
    from src.model import BinaryAsset, SourceFile

    source = SourceFile.parse(wrapper.read_text(errors="replace"))
    existing = source.binary_asset
    source.binary_asset = BinaryAsset(
        filename=existing.filename if existing else wrapper.with_suffix(".pdf").name,
        bytes=ref.size,
        sha256=ref.sha256,
        downloaded_at=existing.downloaded_at if existing else "",
        download_status=existing.download_status if existing else "ok",
        binary_key=ref.key,
        source_sha256=ref.source_sha256,
        source_bytes=ref.source_size,
        optimized=ref.optimized,
    )
    wrapper.write_text(source.render())
