"""Who is asking, and which corpus they may touch."""

from __future__ import annotations

from src.identity.base import (
    BUCKET_PREFIX,
    Workspace,
    WorkspaceResolver,
    default_bucket_name,
)
from src.identity.static import StaticWorkspaceResolver

__all__ = [
    "BUCKET_PREFIX",
    "StaticWorkspaceResolver",
    "Workspace",
    "WorkspaceResolver",
    "default_bucket_name",
]
