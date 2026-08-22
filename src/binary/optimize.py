"""PDF optimization, with the text layer as an invariant rather than a hope.

Implements `context-v/specs/Binary-Ingest-And-Bin-Store.md`, Behaviours 2-4 and 21.

Publishers have no incentive to optimize. Measured on the real corpus, the
Bloomberg annual report is 38 MB and comes out of Ghostscript `/ebook` at
**9.1 MB with its text layer byte-for-byte intact** — 24% of original. Across
78 binaries that is the difference between 282 MB and roughly 70.

Four rules, and three of them are refusals:

1. **`/ebook` (150 DPI), not `/screen`.** `/screen` is 72 DPI and gets to 11%,
   but it is visibly soft full-screen, which is where a client reads a report.
2. **Text below threshold means reject.** Ghostscript only downsamples raster
   images and leaves text vector, so extraction should survive untouched. If it
   does not, something unexpected happened and the original wins. A corpus
   grounds factual claims; an optimization that costs extraction is not a saving.
3. **A scan is never optimized.** Little extractable text means the images *are*
   the content, and downsampling destroys the only thing there.
4. **A missing optimizer degrades, never blocks.** No Ghostscript means store
   verbatim and carry on. Capture failing because a compressor is absent would be
   a self-inflicted outage.

The compressor and extractor are injected so the suite can exercise all four
rules hermetically. Ghostscript's real behaviour is covered by the deliberate run
named in the spec, because a fixture proving `gs` compresses is a fixture proving
nothing.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

#: Below this many extractable characters, the images are the content (rule 3).
SCANNED_TEXT_FLOOR = 200

#: Optimized text must retain at least this share of the original's (rule 2).
TEXT_RETENTION_FLOOR = 0.98

#: Ghostscript preset. See rule 1 before changing it.
DEFAULT_PDF_SETTINGS = "/ebook"

#: Why an optimization did not happen. Carried so the caller can say which.
SKIPPED_NO_OPTIMIZER = "no_optimizer"
SKIPPED_SCANNED = "scanned"
SKIPPED_TEXT_LOSS = "text_loss"
SKIPPED_NOT_SMALLER = "not_smaller"


@dataclass(frozen=True)
class OptimizeResult:
    """What to store, and whether anything was done to it."""

    data: bytes
    optimized: bool
    reason: str = ""

    #: Extractable characters before and after, for the record.
    text_before: int = 0
    text_after: int = 0


def ghostscript_available() -> bool:
    return shutil.which("gs") is not None


def gs_compress(data: bytes, settings: str = DEFAULT_PDF_SETTINGS) -> bytes:
    """Run Ghostscript over PDF bytes. Raises if it is absent or fails."""
    if not ghostscript_available():
        raise FileNotFoundError("ghostscript (gs) is not installed")
    result = subprocess.run(
        [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.5",
            f"-dPDFSETTINGS={settings}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-sOutputFile=-",
            "-",
        ],
        input=data,
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError(result.stderr.decode(errors="replace")[:400] or "gs produced nothing")
    return result.stdout


def pdftotext_extract(data: bytes) -> str:
    """Extract a PDF's text layer. Returns empty string when unavailable."""
    if shutil.which("pdftotext") is None:
        return ""
    result = subprocess.run(["pdftotext", "-", "-"], input=data, capture_output=True)
    return result.stdout.decode(errors="replace") if result.returncode == 0 else ""


def optimize_pdf(
    data: bytes,
    *,
    compress: Callable[[bytes], bytes] | None = None,
    extract_text: Callable[[bytes], str] = pdftotext_extract,
) -> OptimizeResult:
    """Optimize, or explain why it did not.

    Never raises for an expected condition. Every refusal comes back as
    `optimized=False` with a `reason`, because the caller's job is to store
    something either way.
    """
    if compress is None:
        compress = gs_compress if ghostscript_available() else None
    if compress is None:
        # Rule 4 — an absent optimizer must never block a capture.
        return OptimizeResult(data=data, optimized=False, reason=SKIPPED_NO_OPTIMIZER)

    before = len(extract_text(data))
    if before < SCANNED_TEXT_FLOOR:
        # Rule 3 — the images are the content; downsampling would destroy it.
        return OptimizeResult(
            data=data, optimized=False, reason=SKIPPED_SCANNED, text_before=before
        )

    try:
        candidate = compress(data)
    except Exception:
        # A compressor that errors is a compressor that is absent, as far as the
        # capture is concerned. Rule 4 again.
        return OptimizeResult(
            data=data, optimized=False, reason=SKIPPED_NO_OPTIMIZER, text_before=before
        )

    after = len(extract_text(candidate))
    if after < before * TEXT_RETENTION_FLOOR:
        # Rule 2 — extraction is worth more than bytes.
        return OptimizeResult(
            data=data,
            optimized=False,
            reason=SKIPPED_TEXT_LOSS,
            text_before=before,
            text_after=after,
        )

    if len(candidate) >= len(data):
        # Optimizing to something larger is a rewrite for no gain, and it would
        # change the hash of an artifact for nothing.
        return OptimizeResult(
            data=data,
            optimized=False,
            reason=SKIPPED_NOT_SMALLER,
            text_before=before,
            text_after=after,
        )

    return OptimizeResult(data=candidate, optimized=True, text_before=before, text_after=after)
