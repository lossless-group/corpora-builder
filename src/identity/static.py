"""Workspace identity from local configuration.

The first and, during phases 1-6, only implementation. A single operator on one
machine does not need an identity service to tell them which corpus they are
working on.
"""

from __future__ import annotations

from src.identity.base import Workspace, WorkspaceResolver


class StaticWorkspaceResolver(WorkspaceResolver):
    """Returns a workspace supplied at construction time."""

    def __init__(self, slug: str, display_name: str) -> None:
        self.slug = slug
        self.display_name = display_name

    def resolve(self) -> Workspace:
        raise NotImplementedError
