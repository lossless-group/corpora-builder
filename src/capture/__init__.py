"""Turning a link into a filed source."""

from __future__ import annotations

from src.capture.add import EXCERPT_CHARS, AddResult, add_source
from src.capture.fetch import Fetcher, FetchResult, JinaFetcher

__all__ = [
    "EXCERPT_CHARS",
    "AddResult",
    "FetchResult",
    "Fetcher",
    "JinaFetcher",
    "add_source",
]
