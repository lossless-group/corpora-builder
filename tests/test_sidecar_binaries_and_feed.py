"""Covers `context-v/specs/Browse-Corpus.md` behaviours 10-12 — the sidecar
surface for the `bin/` store and the change feed.

Through FastAPI's `TestClient` against a `LocalFsStore`, so nothing here reaches
a network or a bucket. The point under protection is that the screen and the CLI
render the *same* records: a second notion of "what changed" is how two surfaces
start disagreeing about a client's corpus.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.binary.ingest import ingest_binary
from src.binary.store import BinStore
from src.server.app import create_app
from src.store import LocalFsStore

PDF = b"%PDF-1.7\n" + b"a report worth citing " * 200

WRAPPER = """---
title: "A Report"
url: "https://example.org/report.pdf"
fetched_at: 2026-08-01T00:00:00Z
binary_asset:
  filename: "report.pdf"
  content_type: "application/pdf"
  size_bytes: {size}
  sha256: "{sha}"
  binary_key: {key}
  optimized: false
---

Body.
"""


@pytest.fixture()
def wired(tmp_path: Path) -> tuple[TestClient, BinStore, str]:
    """A store holding one source whose binary is really in `bin/`."""
    store = LocalFsStore(tmp_path / "corpus")
    bins = BinStore(store, cache_dir=tmp_path / "cache")
    ref = ingest_binary(bins, PDF, ".pdf", optimize=False).ref
    store.write(
        "live/topics/x/sources/report.md",
        WRAPPER.format(size=len(PDF), sha=ref.sha256, key=ref.key).encode(),
    )
    # `bin_store=bins` matters: without it the app reads the real machine
    # cache and reports `present` for something the test just evicted.
    return TestClient(create_app(store, "test", bin_store=bins)), bins, ref.key


# ---------------------------------------------------------------------------
# a row knows where its binary is
# ---------------------------------------------------------------------------


@pytest.mark.spec("BROWSE-10")
def test_a_row_reports_its_binary_key_and_whether_the_bytes_are_here(
    wired: tuple[TestClient, BinStore, str],
) -> None:
    client, bins, key = wired

    row = client.get("/api/sources").json()["rows"][0]

    assert row["binary_key"] == key
    assert row["binary_state"] == "present"  # ingest populated the cache
    assert row["binary_bytes"] == len(PDF)

    # Evict and the same row reports the absence as a state, not an error.
    from src.binary.keys import BinaryRef

    assert bins.evict(BinaryRef.from_key(key)).ok is True
    row = client.get("/api/sources").json()["rows"][0]
    assert row["binary_state"] == "not_downloaded"
    assert row["binary_key"] == key  # still carries what you need to get it


# ---------------------------------------------------------------------------
# the feed, through the sidecar
# ---------------------------------------------------------------------------


@pytest.mark.spec("BROWSE-11")
def test_the_change_feed_is_served_as_the_same_records_the_cli_renders(
    wired: tuple[TestClient, BinStore, str], tmp_path: Path
) -> None:
    client, _, _ = wired
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    import os

    def run(*a: str) -> None:
        subprocess.run(
            ["git", *a], cwd=repo, env={**os.environ, **env}, check=True, capture_output=True
        )

    run("init", "-q", "-b", "main")
    (repo / "corpus").mkdir()
    (repo / "corpus" / "a.md").write_text("x")
    run("add", "-A")
    run("commit", "-q", "-m", "capture(a): the first source")

    body = client.get("/api/changes", params={"repo": str(repo), "prefix": "corpus"}).json()

    assert body["count"] == 1
    entry = body["changes"][0]
    assert entry["verb"] == "capture" and entry["sentence"] == "the first source"
    assert entry["added"] == ["corpus/a.md"]
    assert body["truncated"] is False


@pytest.mark.spec("BROWSE-11")
def test_a_path_that_is_not_a_repository_is_a_client_error_not_a_crash(
    wired: tuple[TestClient, BinStore, str], tmp_path: Path
) -> None:
    client, _, _ = wired
    r = client.get("/api/changes", params={"repo": str(tmp_path / "nope")})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# fetching — the one read that writes, and only to the cache
# ---------------------------------------------------------------------------


@pytest.mark.spec("BROWSE-12")
def test_fetching_a_binary_works_on_a_read_only_server_and_writes_only_the_cache(
    wired: tuple[TestClient, BinStore, str],
) -> None:
    client, bins, key = wired
    from src.binary.keys import BinaryRef

    assert bins.evict(BinaryRef.from_key(key)).ok is True
    before = sorted(bins.remote.list(""))

    r = client.get("/api/binary", params={"key": key})

    assert r.status_code == 200
    assert r.content == PDF
    assert bins.is_cached(key)  # the cache was populated
    assert sorted(bins.remote.list("")) == before  # the store was not touched


@pytest.mark.spec("BROWSE-13")
@pytest.mark.parametrize(
    "key",
    ["live/topics/x/sources/report.md", "bin/../live/secret.md", "../../etc/passwd"],
    ids=["not-a-bin-key", "traversal", "absolute-escape"],
)
def test_a_key_outside_bin_is_refused(wired: tuple[TestClient, BinStore, str], key: str) -> None:
    client, _, _ = wired
    assert client.get("/api/binary", params={"key": key}).status_code == 400


@pytest.mark.spec("BROWSE-10")
def test_an_older_binary_asset_spelling_still_reports_a_size(tmp_path: Path) -> None:
    """reach-edu carries at least three `binary_asset` shapes. Uploaded PDFs use
    `bytes`/`original_bytes`/`compressed`; fetched ones use `size_bytes`. A row
    that renders 0 B because it met the wrong synonym is a bug the reader sees."""
    store = LocalFsStore(tmp_path / "corpus")
    bins = BinStore(store, cache_dir=tmp_path / "cache")
    ref = ingest_binary(bins, PDF, ".pdf", optimize=False).ref
    store.write(
        "live/x/sources/old.md",
        (
            '---\ntitle: "Older Shape"\nbinary_asset:\n'
            '  filename: "a.pdf"\n'
            "  bytes: 4251753\n"
            "  original_bytes: 6882194\n"
            "  compressed: true\n"
            f"  binary_key: {ref.key}\n"
            "  optimized: false\n---\n\nBody.\n"
        ).encode(),
    )
    client = TestClient(create_app(store, "t", bin_store=bins))

    row = client.get("/api/sources").json()["rows"][0]

    assert row["binary_bytes"] == 4251753  # not 0
    assert row["binary_optimized"] is True  # `compressed` counts
