"""`python -m src.server` — the entry point the Tauri shell spawns.

Mirrors memopop-orchestrator's `src/server/__main__.py`, whose Rust
`SidecarManager` invokes `{repo}/.venv/bin/python -m src.server`. Copying that
shape means the Rust side is a copy rather than a design.

One deliberate difference: memopop's sidecar lives in a SEPARATE repo the
operator has to locate and anchor before anything works, which is the first step
of its onboarding and the first thing that goes wrong. corpora-builder's Python
is in this repo, beside the app, so the path is known and there is nothing to
anchor.

Environment:
    CORPORA_LOCAL      serve a local directory instead of R2
    CORPORA_WRITABLE   "1" to enable capture (see Capture-From-The-Screen)
    CORPORA_PORT       default 8787
"""

from __future__ import annotations

import os

import uvicorn

from src.cli import build_store, load_env
from src.server.app import create_app


def run() -> None:
    env = load_env()
    local = os.environ.get("CORPORA_LOCAL", "")
    store, workspace = build_store(env, local)
    label = local or f"{workspace.display_name} ({workspace.bucket})"

    uvicorn.run(
        create_app(store, label, writable=os.environ.get("CORPORA_WRITABLE") == "1"),
        host="127.0.0.1",
        port=int(os.environ.get("CORPORA_PORT", "8787")),
        log_level="warning",
    )


if __name__ == "__main__":
    run()
