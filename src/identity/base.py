"""The workspace seam — static config now, didi.sh later.

The operator's ask was to pull workspace details from the didi.sh account and
workspace. Most of that is available: increment 1 of `id-didi-sh` ships
`didi_id`, domain-as-id orgs, five roles including `editor`/`viewer`, and local
EdDSA verification via JWKS.

Two things are not, and they are why this is a seam rather than a client:

1. **Workspaces do not exist in didi.sh yet.** `GET /api/me` returns org + role.
   Today workspace collapses onto org, which holds until one org needs two
   isolated corpora or a person belongs somewhere their email domain does not
   imply.
2. **A CLI has nowhere to put a `didi_session` cookie.** It is browser-issued,
   HttpOnly, ~12h. Phases 1-6 are a terminal; Phase 7's Tauri webview is where
   the existing flow works unmodified.

Full enumeration:
`id-didi-sh/context-v/explorations/What-Corpora-Builder-Needs-From-didi-sh.md`.

The invariant that makes the eventual swap free: **nothing outside this module
names a bucket.** `bucket_for` is the only place the naming rule lives, and
`R2Store` takes its bucket as a required argument with no default.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

#: Every corpus bucket is `corpora-<workspace-slug>`. One bucket per workspace,
#: because R2 API tokens scope per-bucket — which makes the isolation boundary
#: structural rather than a policy we have to remember to enforce.
BUCKET_PREFIX = "corpora-"


@dataclass(frozen=True)
class Workspace:
    """The unit a corpus belongs to. One workspace, one bucket."""

    slug: str
    display_name: str


class WorkspaceResolver(ABC):
    """Answers 'which workspace am I operating on?'"""

    @abstractmethod
    def resolve(self) -> Workspace:
        """Return the active workspace."""


def bucket_for(workspace: Workspace) -> str:
    """The R2 bucket holding `workspace`'s corpus."""
    raise NotImplementedError
