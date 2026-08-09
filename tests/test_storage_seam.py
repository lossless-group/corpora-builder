"""Tests for the storage seam — spec: context-v/specs/Storage-Seam.md.

The conformance suite is the point. Every `STORE-01`..`STORE-10` test takes the
parametrized `store` fixture and therefore runs once per backend, and **no test
body branches on which backend it got**. A seam whose tests have to know what is
behind it is not a seam — it is an interface someone wrote down.

The fixture branches, once, to construct each backend. That is the only place
implementation names appear in this file, and `STORE-11` is the guard that keeps
it honest: it fails if a concrete `CorpusStore` exists that the fixture does not
exercise. When the parked BTRFS/ZFS option re-opens at Phase 7 and a `PosixStore`
appears, that test is what forces it through the same suite.

R2 runs against `moto` in-process so the suite stays offline and fast. moto
proving a boto3 client correct is NOT R2 accepting it, so a real dev-bucket run
is gated behind `CORPORA_R2_DEV_BUCKET` and done by hand before the phase is
called done — see the spec's "Not in the automated suite" section.

Everything writes under `tmp_path` or an in-process mock. No client corpus is
ever touched: `augment-it/clients/*/corpus/` is on the Autonomy-Gates RED list.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from src.identity import (
    BUCKET_PREFIX,
    StaticWorkspaceResolver,
    Workspace,
    bucket_for,
)
from src.store import CachedStore, CorpusStore, KeyNotFound, LocalFsStore, R2Store

#: The backends the conformance suite covers. `STORE-11` asserts this is every
#: concrete store there is, so adding one without adding it here fails the build.
BACKENDS = ["LocalFsStore", "R2Store"]

TEST_BUCKET = "corpora-test-workspace"


@pytest.fixture(params=BACKENDS)
def store(request: pytest.FixtureRequest, tmp_path: Path):
    """One conformance run per backend.

    This is the ONLY place in this file that names an implementation. Test
    bodies below receive a `CorpusStore` and must not care which one.
    """
    if request.param == "LocalFsStore":
        yield LocalFsStore(tmp_path)
    else:
        with mock_aws():
            client = boto3.client("s3", region_name="us-east-1")
            client.create_bucket(Bucket=TEST_BUCKET)
            yield R2Store(bucket=TEST_BUCKET, client=client)


# ---------------------------------------------------------------------------
# The conformance suite — runs against every backend, branches in none of them
# ---------------------------------------------------------------------------


@pytest.mark.spec("STORE-01")
def test_written_bytes_read_back_identical(store: CorpusStore) -> None:
    store.write("live/topic/ocean-energy/index.md", b"# Ocean Energy\n")

    assert store.read("live/topic/ocean-energy/index.md") == b"# Ocean Energy\n"


@pytest.mark.spec("STORE-02")
def test_reading_a_missing_key_raises(store: CorpusStore) -> None:
    """Never empty bytes. A silent empty read is how a corrupt corpus looks fine."""
    with pytest.raises(KeyNotFound):
        store.read("live/topic/never-written.md")


@pytest.mark.spec("STORE-03")
def test_exists_flips_on_write(store: CorpusStore) -> None:
    assert store.exists("live/a.md") is False

    store.write("live/a.md", b"x")

    assert store.exists("live/a.md") is True


@pytest.mark.spec("STORE-04")
def test_list_filters_by_prefix_and_sorts(store: CorpusStore) -> None:
    store.write("live/thesis/b.md", b"b")
    store.write("live/thesis/a.md", b"a")
    store.write("live/strategy/c.md", b"c")

    assert store.list("live/thesis/") == ["live/thesis/a.md", "live/thesis/b.md"]


@pytest.mark.spec("STORE-05")
def test_list_is_recursive_and_returns_full_keys(store: CorpusStore) -> None:
    """Not a directory listing — one level down or ten, you get the whole key."""
    store.write("live/thesis/consumer-immunology/sources/2026-08-08_paper.md", b"x")

    assert store.list("live/") == ["live/thesis/consumer-immunology/sources/2026-08-08_paper.md"]


@pytest.mark.spec("STORE-06")
def test_delete_removes_the_key(store: CorpusStore) -> None:
    store.write("live/gone.md", b"x")

    store.delete("live/gone.md")

    assert store.exists("live/gone.md") is False
    with pytest.raises(KeyNotFound):
        store.read("live/gone.md")


@pytest.mark.spec("STORE-07")
def test_stat_reports_size_and_a_content_sensitive_hash(store: CorpusStore) -> None:
    store.write("live/a.md", b"hello")
    first = store.stat("live/a.md")

    store.write("live/a.md", b"hello world")
    second = store.stat("live/a.md")

    assert first.size == 5
    assert second.size == 11
    assert first.content_hash != second.content_hash


@pytest.mark.spec("STORE-08")
def test_overwrite_replaces_without_error(store: CorpusStore) -> None:
    store.write("live/a.md", b"first")
    store.write("live/a.md", b"second")

    assert store.read("live/a.md") == b"second"


@pytest.mark.spec("STORE-09")
def test_non_utf8_binary_round_trips(store: CorpusStore) -> None:
    """PDFs ride alongside their markdown as citable artifacts. Not hypothetical."""
    payload = b"%PDF-1.7\x00\x01\x02\xff\xfe binary \x00 tail"

    store.write("live/topic/x/sources/2026-08-08_report.pdf", payload)

    assert store.read("live/topic/x/sources/2026-08-08_report.pdf") == payload


@pytest.mark.spec("STORE-10")
def test_non_ascii_and_spaced_keys_round_trip(store: CorpusStore) -> None:
    key = "live/topic/café-münchen/sources/2026-08-08_a report.md"

    store.write(key, b"x")

    assert store.read(key) == b"x"
    assert store.list("live/topic/café-münchen/") == [key]


# ---------------------------------------------------------------------------
# The guard that keeps the seam a seam
# ---------------------------------------------------------------------------


@pytest.mark.spec("STORE-11")
def test_every_concrete_backend_is_covered_by_the_conformance_fixture() -> None:
    """Adding a backend without adding it to BACKENDS fails here.

    `CachedStore` is excluded on purpose: it is a decorator over another store,
    not a substrate, and it has its own tests below. Everything else that claims
    to be a `CorpusStore` must survive the same suite — that is the promise the
    parked BTRFS/ZFS option was deferred on.
    """
    concrete = {c.__name__ for c in CorpusStore.__subclasses__()} - {"CachedStore"}

    assert concrete == set(BACKENDS)


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------


class CountingStore(LocalFsStore):
    """A `LocalFsStore` that records how often the backing read was reached."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reads = 0

    def read(self, key: str) -> bytes:
        self.reads += 1
        return super().read(key)


@pytest.mark.spec("STORE-12")
def test_repeat_read_does_not_reach_the_backing_store(tmp_path: Path) -> None:
    backing = CountingStore(tmp_path)
    cached = CachedStore(backing)
    cached.write("live/a.md", b"x")

    cached.read("live/a.md")
    cached.read("live/a.md")

    assert backing.reads == 1


@pytest.mark.spec("STORE-13")
def test_write_through_the_cache_invalidates_it(tmp_path: Path) -> None:
    """A stale cache must never win."""
    cached = CachedStore(LocalFsStore(tmp_path))
    cached.write("live/a.md", b"first")
    cached.read("live/a.md")

    cached.write("live/a.md", b"second")

    assert cached.read("live/a.md") == b"second"


# ---------------------------------------------------------------------------
# Workspace identity
# ---------------------------------------------------------------------------


@pytest.mark.spec("WORKSPACE-01")
def test_static_resolver_returns_its_configured_workspace() -> None:
    resolver = StaticWorkspaceResolver(slug="reach-edu", display_name="Reach Edu")

    workspace = resolver.resolve()

    assert workspace == Workspace(slug="reach-edu", display_name="Reach Edu")


@pytest.mark.spec("WORKSPACE-02")
def test_bucket_name_derives_from_the_workspace_slug() -> None:
    workspace = Workspace(slug="reach-edu", display_name="Reach Edu")

    assert bucket_for(workspace) == f"{BUCKET_PREFIX}reach-edu"


@pytest.mark.spec("WORKSPACE-02")
def test_r2store_has_no_default_bucket() -> None:
    """No call site may carry a literal bucket name.

    Enforced structurally rather than by convention: with no default, an R2Store
    cannot be constructed without someone deriving the name from a resolved
    workspace. That is what makes the eventual didi.sh resolver a swap.
    """
    bucket_param = inspect.signature(R2Store.__init__).parameters["bucket"]

    assert bucket_param.default is inspect.Parameter.empty
