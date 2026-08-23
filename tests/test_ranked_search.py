"""Covers the Python half of `context-v/specs/Ranked-Search.md`.

The ranking itself is exercised in `app/src/lib/search.test.ts`, against a real
bundle built by the real builder — a hand-rolled fake of a search engine would
prove nothing about stemming or ranking, which are the only reasons to have one.
What lives here is everything Pagefind is NOT allowed to do: touch a source,
fail when Node is missing, or be served with a content type its runtime refuses.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.index.manifest import save_manifest
from src.index.rebuild import reindex
from src.index.search_index import (
    BUNDLE_FINGERPRINT_KEY,
    BUNDLE_PREFIX,
    build_search_index,
    bundle_content_type,
)
from src.server.app import create_app
from src.server.browse import build_manifest
from src.store import LocalFsStore

needs_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="the Pagefind builder is a Node program; the Python side degrades rather than failing",
)

SOURCE = """---
title: "{title}"
url: "https://example.org/{slug}"
fetched_at: "2026-01-0{n}T00:00:00Z"
status: "fetched"
domains:
  - "strategy:workforce-development"
---

A paragraph of genuine prose about apprenticeship funding in rural counties, long
enough to survive the excerpt rule that skips navigation chrome.
"""


@pytest.fixture()
def store(tmp_path: Path) -> LocalFsStore:
    s = LocalFsStore(tmp_path / "corpus")
    for n, title in enumerate(["Apprenticeship Report", "Skills Gap Study"], start=1):
        s.write(
            f"live/strategies/workforce-development/sources/2026-01-0{n}_s.md",
            SOURCE.format(title=title, slug=title.lower().replace(" ", "-"), n=n).encode(),
        )
    return s


@pytest.mark.spec("SEARCH-08")
@needs_node
def test_building_the_index_writes_only_derived_keys(store: LocalFsStore) -> None:
    """A search index that could modify a source would be a browse tool with a
    hidden write path — the exact accident `--writable` exists to prevent."""
    before = {k: store.read(k) for k in store.list("")}

    result = reindex(store)

    assert result.search.ok and not result.search.skipped
    assert result.search.records == 2

    after = {k: store.read(k) for k in store.list("")}
    for key, blob in before.items():
        assert after[key] == blob, f"{key} was modified"

    new_keys = set(after) - set(before)
    assert new_keys, "something was written"
    assert all(k.startswith("index/") for k in new_keys), sorted(new_keys)
    assert any(k.startswith(BUNDLE_PREFIX) for k in new_keys)


@pytest.mark.spec("SEARCH-08")
@needs_node
def test_a_rebuild_leaves_no_orphans_behind(store: LocalFsStore) -> None:
    """Pagefind chunks its index by content, so a rebuild after a deletion can
    produce fewer files than the last one. Anything left over is a chunk the
    runtime would happily fetch and read as current."""
    reindex(store)
    stale = f"{BUNDLE_PREFIX}fragment/en_deadbeef.pf_fragment"
    store.write(stale, b"a chunk from a previous build")

    reindex(store)

    assert stale not in store.list(BUNDLE_PREFIX)


@pytest.mark.spec("SEARCH-08")
@needs_node
def test_a_rebuild_resends_only_what_is_not_content_addressed(store: LocalFsStore) -> None:
    """Measured on an 845-source corpus: the bundle is 866 objects, because
    Pagefind writes one fragment per record. Rewriting all of them on every
    rebuild is ~1,700 operations against a client's bucket for a corpus that may
    have gained a single source.

    Fragment, index and filter files are named by a hash of their own contents,
    so a key already in the store is already right.
    """
    first = reindex(store)
    assert first.search.written == first.search.files, "the first build sends everything"

    second = reindex(store)

    assert second.search.files == first.search.files
    assert second.search.written < second.search.files
    resent = second.search.written
    assert resent <= 20, f"an unchanged rebuild resent {resent} files"
    # ...and what WAS resent is exactly the un-addressed set at the bundle root.
    roots = [k for k in store.list(BUNDLE_PREFIX) if "/" not in k[len(BUNDLE_PREFIX) :]]
    assert resent == len(roots)


@pytest.mark.spec("SEARCH-08")
@needs_node
def test_the_bundle_records_the_manifest_it_was_built_from(store: LocalFsStore) -> None:
    """A content fingerprint, not a clock: reindexing an unchanged corpus must
    not make every bundle look stale."""
    first = reindex(store)

    assert store.read(BUNDLE_FINGERPRINT_KEY).decode() == first.fingerprint

    second = reindex(store)
    assert second.fingerprint == first.fingerprint


@pytest.mark.spec("SEARCH-09")
def test_no_node_is_a_skip_with_a_reason_not_a_failure(
    store: LocalFsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`scripts/check.sh` already skips its Node rungs rather than failing, so
    the Python side stays runnable on a machine that has never built the
    frontend. Reindexing does the same — and the manifest, which is what the
    listing actually depends on, is still written."""
    monkeypatch.setattr("src.index.search_index.shutil.which", lambda _: None)

    result = reindex(store)

    assert result.search.ok, "a missing toolchain is not a failure"
    assert result.search.skipped == "node is not on PATH"
    assert not result.search.error
    assert result.sources == 2, "the manifest is written regardless"
    assert not any(k.startswith(BUNDLE_PREFIX) for k in store.list(""))


@pytest.mark.spec("SEARCH-09")
def test_a_build_that_runs_and_fails_is_not_a_skip(
    store: LocalFsStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two must not be confused. A skip means "nothing tried"; a failure
    means "tried, and the index is not there" — and only one of them should
    ever be quiet."""
    monkeypatch.setattr("src.index.search_index.BUILDER", Path("/nonexistent/builder.mjs"))

    result = build_search_index(store, save_manifest(store, build_manifest(store)))

    assert result.ok and result.skipped.startswith("builder not found")


@pytest.mark.spec("SEARCH-10")
@needs_node
def test_the_sidecar_serves_the_bundle_with_usable_content_types(store: LocalFsStore) -> None:
    """The WebAssembly module is the one that matters: a browser refuses to
    stream-compile anything not served as `application/wasm`, and Pagefind's
    fallback is slower and quieter about it."""
    reindex(store)
    client = TestClient(create_app(store, "test"))

    js = client.get("/pagefind/pagefind.js")
    assert js.status_code == 200
    assert "javascript" in js.headers["content-type"]

    entry = client.get("/pagefind/pagefind-entry.json")
    assert entry.status_code == 200
    assert "json" in entry.headers["content-type"]

    wasm_key = next(k for k in store.list(BUNDLE_PREFIX) if k.endswith(".pagefind"))
    wasm = client.get(f"/pagefind/{wasm_key[len(BUNDLE_PREFIX):]}")
    assert wasm.status_code == 200
    assert wasm.headers["content-type"].startswith("application/wasm")

    assert bundle_content_type("wasm.en.pagefind") == "application/wasm"


@pytest.mark.spec("SEARCH-10")
def test_a_path_escaping_the_bundle_is_refused(store: LocalFsStore) -> None:
    reindex(store, search=False)
    client = TestClient(create_app(store, "test"))

    escaped = client.get("/pagefind/%2e%2e/sources.jsonl")
    assert escaped.status_code == 400

    missing = client.get("/pagefind/never-built.js")
    assert missing.status_code == 404


@pytest.mark.spec("SEARCH-10")
def test_reindex_is_writable_only(store: LocalFsStore) -> None:
    """Gated exactly like capture: it reads every source and writes into the
    corpus, and the first thing this surface was ever pointed at was a client
    corpus on the RED list."""
    read_only = TestClient(create_app(store, "test", writable=False))
    assert read_only.post("/api/reindex").status_code == 403

    writable = TestClient(create_app(store, "test", writable=True))
    body = writable.post("/api/reindex").json()
    assert body["sources"] == 2
    assert body["fingerprint"]
