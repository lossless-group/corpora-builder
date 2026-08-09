"""Workspace identity from local configuration.

The first implementation, and during phases 1-6 the only one. A single operator
on one machine does not need an identity service to tell them which corpus they
are working on.

`from_env` is the seam's whole point in miniature: one variable names the
workspace, and its storage location is looked up rather than assembled at a call
site. When didi.sh grows a workspace claim, a `DidiWorkspaceResolver` replaces
this class and nothing above it changes.
"""

from __future__ import annotations

import os

from src.identity.base import Workspace, WorkspaceResolver, default_bucket_name


class StaticWorkspaceResolver(WorkspaceResolver):
    """Returns a workspace supplied at construction time."""

    def __init__(
        self,
        slug: str,
        display_name: str,
        bucket: str | None = None,
        prefix: str = "",
    ) -> None:
        self.slug = slug
        self.display_name = display_name
        self.bucket = bucket or default_bucket_name(slug)
        self.prefix = prefix

    def resolve(self) -> Workspace:
        return Workspace(
            slug=self.slug,
            display_name=self.display_name,
            bucket=self.bucket,
            prefix=self.prefix,
        )

    @classmethod
    def from_env(cls) -> StaticWorkspaceResolver:
        """Build from CORPORA_WORKSPACE / CORPORA_R2_BUCKET / CORPORA_R2_PREFIX."""
        slug = os.environ.get("CORPORA_WORKSPACE", "")
        if not slug:
            raise RuntimeError("CORPORA_WORKSPACE is not set")
        return cls(
            slug=slug,
            display_name=os.environ.get("CORPORA_WORKSPACE_NAME", slug),
            bucket=os.environ.get("CORPORA_R2_BUCKET") or None,
            prefix=os.environ.get("CORPORA_R2_PREFIX", ""),
        )
