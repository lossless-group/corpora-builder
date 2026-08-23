"""The source-file schema, as code."""

from __future__ import annotations

from src.model.frontmatter import StrandedContent, parse_frontmatter, render_frontmatter
from src.model.naming import slugify, source_filename
from src.model.source import (
    FIELD_ALIASES,
    FIELD_ORDER,
    VALID_STATUS,
    BinaryAsset,
    SourceFile,
)
from src.model.text import prose_excerpt
from src.model.urls import normalize_url

__all__ = [
    "FIELD_ALIASES",
    "FIELD_ORDER",
    "VALID_STATUS",
    "BinaryAsset",
    "SourceFile",
    "StrandedContent",
    "normalize_url",
    "parse_frontmatter",
    "prose_excerpt",
    "render_frontmatter",
    "slugify",
    "source_filename",
]
