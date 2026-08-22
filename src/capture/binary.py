"""Binary siblings — the PDF that rides alongside its markdown.

Downloaded rather than linked because remote URLs rot over months and years, and
because Jina's text extraction loses the page and figure fidelity a citation
needs. The local copy is the durable artifact.

Recorded even on failure. An absent `binary_asset` cannot distinguish "we never
tried" from "we tried and got a 403"; `download_status` can.
"""

from __future__ import annotations

import hashlib

from src.binary.keys import BinaryRef
from src.model import BinaryAsset

#: Content types that get a sibling. Deliberately narrow — a corpus of
#: everything-the-web-served is not a corpus.
BINARY_TYPES = ("application/pdf",)


def is_binary(url: str, content_type: str) -> bool:
    """Whether this resource should be stored as a binary sibling."""
    if content_type and content_type.split(";")[0].strip().lower() in BINARY_TYPES:
        return True
    return url.split("?")[0].lower().endswith(".pdf")


def build_binary_asset(
    filename: str,
    data: bytes,
    downloaded_at: str,
    status: str,
    ref: BinaryRef | None = None,
) -> BinaryAsset:
    """Describe a stored (or failed) binary.

    Called on the failure path too, with empty `data` and no `ref` — which is the
    point. The block records that a binary was expected and what happened to it,
    and a failure leaves no `binary_key` because nothing was stored.

    When `ref` is present it is authoritative: `sha256` and `bytes` describe what
    is actually in `bin/`, which is the optimized artifact when one was accepted,
    while `source_*` preserves what the publisher served.
    """
    if ref is not None:
        return BinaryAsset(
            filename=filename,
            bytes=ref.size,
            sha256=ref.sha256,
            downloaded_at=downloaded_at,
            download_status=status,
            binary_key=ref.key,
            source_sha256=ref.source_sha256,
            source_bytes=ref.source_size,
            optimized=ref.optimized,
        )
    return BinaryAsset(
        filename=filename,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest() if data else "",
        downloaded_at=downloaded_at,
        download_status=status,
    )
