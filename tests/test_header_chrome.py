"""Covers `context-v/specs/Header-Chrome.md` — the server half.

The mode toggle's own rules are pure TypeScript and live in
`app/src/lib/mode.svelte.ts`, tested by the frontend suite; both land in the same
ledger.
"""

from __future__ import annotations

import os
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.identity import StaticWorkspaceResolver, Workspace
from src.identity.base import humanise
from src.server.app import create_app
from src.store import LocalFsStore


@pytest.mark.spec("HEADER-01")
def test_a_display_name_is_derived_from_the_slug() -> None:
    """`display_name` used to default to the slug, which is how the header came
    to read `reach-edu (reach-edu)` — a slug printed twice."""
    with mock.patch.dict(os.environ, {"CORPORA_WORKSPACE": "reach-edu"}, clear=True):
        ws = StaticWorkspaceResolver.from_env().resolve()

    assert ws.display_name == "Reach Edu"
    assert ws.slug == "reach-edu"  # the identity itself is untouched

    assert humanise("humain-vc") == "Humain Vc"
    assert humanise("a") == "A"
    assert humanise("") == ""


@pytest.mark.spec("HEADER-02")
def test_a_configured_name_beats_the_derived_one() -> None:
    """No rule turns `ncad-forge` into `NCAD-Forge`.

    Deriving a name is a guess, and a guess must lose to a stated answer — the
    alternative is a wrong name in front of a client rather than an approximate
    one.
    """
    env = {"CORPORA_WORKSPACE": "ncad-forge", "CORPORA_WORKSPACE_NAME": "NCAD-Forge"}
    with mock.patch.dict(os.environ, env, clear=True):
        ws = StaticWorkspaceResolver.from_env().resolve()

    assert ws.display_name == "NCAD-Forge"


@pytest.mark.spec("HEADER-03")
def test_meta_hands_over_fields_not_a_rendered_label(tmp_path) -> None:
    """A server that pre-renders a label has made a layout decision for the
    client and taken away the only thing the client is for. The header wants the
    name in the trigger and the slug in the dropdown; only the client knows that.
    """
    store = LocalFsStore(tmp_path / "corpus")
    ws = Workspace(slug="reach-edu", display_name="Reach Edu", bucket="corpora-reach-edu")

    body = TestClient(create_app(store, "Reach Edu", workspace=ws)).get("/api/meta").json()

    assert body["workspace"]["display_name"] == "Reach Edu"
    assert body["workspace"]["slug"] == "reach-edu"
    assert body["workspace"]["bucket"] == "corpora-reach-edu"
    # The two are separable — no "Name (slug)" string anywhere in the payload.
    assert "reach-edu (reach-edu)" not in str(body)


@pytest.mark.spec("HEADER-03")
def test_meta_still_answers_without_a_workspace(tmp_path) -> None:
    """A local `--local <dir>` run has no workspace. It must still paint."""
    store = LocalFsStore(tmp_path / "corpus")

    body = TestClient(create_app(store, "scratch")).get("/api/meta").json()

    assert body["workspace"]["display_name"] == "scratch"
    assert body["workspace"]["bucket"] == ""
