"""Binary siblings — the PDF that rides alongside its markdown.

Downloaded rather than linked because remote URLs rot over months and years, and
because Jina's text extraction loses the page and figure fidelity a citation
needs. The local copy is the durable artifact.

Recorded even on failure. An absent `binary_asset` cannot distinguish "we never
tried" from "we tried and got a 403"; `download_status` can.
"""

from __future__ import annotations

import hashlib

from src.model import BinaryAsset

#: Content types that get a sibling. Deliberately narrow — a corpus of
#: everything-the-web-served is not a corpus.
BINARY_TYPES = ("application/pdf",)


def is_binary(url: str, content_type: str) -> bool:
    """Whether this resource should be stored as a binary sibling."""
    if content_type and content_type.split(";")[0].strip().lower() in BINARY_TYPES:
        return True
    return url.split("?")[0].lower().endswith(".pdf")


def build_binary_asset(filename: str, data: bytes, downloaded_at: str, status: str) -> BinaryAsset:
    """Describe a downloaded (or failed) binary.

    Called on the failure path too, with empty `data` — which is the point. The
    block records that a binary was expected and what happened to it.
    """
    return BinaryAsset(
        filename=filename,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest() if data else "",
        downloaded_at=downloaded_at,
        download_status=status,
    )
