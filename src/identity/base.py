"""The workspace seam — static config now, didi.sh later.

The operator's instinct, mid-Phase-1: *"you should probably make me login with
didi.sh and that should be a workspace variable for reach-edu?"* That is exactly
right as a destination, and it is what this module exists to make cheap.

Two things stop it being today's work, both enumerated in
`id-didi-sh/context-v/explorations/What-Corpora-Builder-Needs-From-didi-sh.md`:

1. **didi.sh has no workspace claim.** `GET /api/me` returns org + role, where
   org is a *domain* (`lossless.group`). `reach-edu` is a client slug, not an
   email domain, so there is nothing there to read yet.
2. **A CLI has nowhere to put a `didi_session` cookie.** Browser-issued,
   HttpOnly, ~12h.

So the workspace comes from config today and from a login later. What makes that
a swap rather than a rewrite is the rule below.

**A workspace carries its own storage location.** Phase 1 originally assumed the
bucket was derivable — `corpora-<slug>` — and reality disagreed on first contact:
the real corpus lives in bucket `reach-edu` under prefix `corpora/`. Buckets are
provisioned by people, sometimes before this tool existed, so a derivation rule
cannot be the source of truth. It survives only as the default for *new*
workspaces.

The invariant that keeps the swap free: **nothing outside a resolver names a
bucket or a prefix.** Call sites ask for a `Workspace` and pass it along.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

#: The naming convention applied when PROVISIONING a new workspace's bucket.
#: Not a lookup — existing workspaces carry their real bucket on the record.
BUCKET_PREFIX = "corpora-"


@dataclass(frozen=True)
class Workspace:
    """The unit a corpus belongs to, and where its bytes actually live.

    `prefix` is a storage detail: keys are scoped under it transparently, so
    nothing above the store ever sees it. That is what lets one client bucket
    hold a corpus beside whatever else the client already keeps there.
    """

    slug: str
    display_name: str
    bucket: str
    prefix: str = ""


class WorkspaceResolver(ABC):
    """Answers 'which workspace am I operating on, and where does it live?'"""

    @abstractmethod
    def resolve(self) -> Workspace:
        """Return the active workspace."""


def default_bucket_name(slug: str) -> str:
    """The bucket a NEWLY PROVISIONED workspace should get.

    One bucket per workspace, because R2 API tokens scope per-bucket — which
    makes the isolation boundary structural rather than a policy someone has to
    remember. Existing workspaces may sit anywhere; ask the resolver, not this.
    """
    return f"{BUCKET_PREFIX}{slug}"
