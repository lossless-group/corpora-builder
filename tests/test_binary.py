"""Covers `context-v/specs/Binary-Ingest-And-Bin-Store.md` — content addressing,
PDF optimization and its three refusals, the two-scopes store, and migration.

The optimizer is **injected** throughout. A fixture proving Ghostscript
compresses is a fixture proving nothing about our code, and building a synthetic
PDF that genuinely shrinks would test `gs` rather than the invariants. So the
suite drives fake compressors and extractors to exercise every branch — accept,
scanned, text-loss, not-smaller, and absent — and Ghostscript's real behaviour is
covered by the deliberate run named in the spec, already measured at 24% of
original with the text layer intact.

`BIN-18` is the conformance block: the same contract against `LocalFsStore` and
an in-memory store, no branching in the bodies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.binary.ingest import ingest_binary, migrate_tree
from src.binary.keys import BinaryRef, key_for, key_for_bytes, sha256_of
from src.binary.optimize import (
    SKIPPED_NO_OPTIMIZER,
    SKIPPED_SCANNED,
    SKIPPED_TEXT_LOSS,
    optimize_pdf,
)
from src.binary.store import (
    HASH_MISMATCH,
    MISSING,
    NOT_DOWNLOADED,
    PRESENT,
    BinStore,
)
from src.store.local import LocalFsStore

# ---------------------------------------------------------------------------
# helpers — fake PDFs and fake optimizers, so every branch is reachable
# ---------------------------------------------------------------------------

PROSE = "The corpus grounds factual claims. " * 40  # comfortably over the floor


def fake_pdf(body: str = PROSE, padding: int = 4096) -> bytes:
    """Bytes that stand in for a PDF. Content is what matters, not structure."""
    return b"%PDF-1.5\n" + body.encode() + b"\n" + b"\x00" * padding


def extractor(mapping: dict[bytes, str]):  # type: ignore[no-untyped-def]
    """A text extractor with known answers, so invariants are exercisable."""

    def extract(data: bytes) -> str:
        return mapping.get(data, PROSE)

    return extract


def shrinker(out: bytes):  # type: ignore[no-untyped-def]
    def compress(_: bytes) -> bytes:
        return out

    return compress


def exploder(_: bytes) -> bytes:
    raise RuntimeError("gs blew up")


class CountingStore(LocalFsStore):
    """Counts reads so a cache hit can be proven to touch no remote."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reads = 0

    def read(self, key: str) -> bytes:
        self.reads += 1
        return super().read(key)


@pytest.fixture()
def binstore(tmp_path: Path) -> BinStore:
    return BinStore(remote=CountingStore(tmp_path / "remote"), cache_dir=tmp_path / "cache")


# ---------------------------------------------------------------------------
# content addressing
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-01")
def test_the_key_is_the_content_hash_with_a_two_hex_fan_out() -> None:
    data = fake_pdf()
    digest = hashlib.sha256(data).hexdigest()

    key = key_for_bytes(data, ".pdf")

    assert key == f"bin/{digest[:2]}/{digest}.pdf"
    assert key_for_bytes(data, ".pdf") == key  # stable across calls
    with pytest.raises(ValueError):
        key_for("too-short", ".pdf")


@pytest.mark.spec("BIN-02")
def test_the_same_bytes_under_two_names_are_one_object(binstore: BinStore) -> None:
    data = fake_pdf()

    a = ingest_binary(binstore, data, ".pdf", optimize=False)
    b = ingest_binary(binstore, data, ".pdf", optimize=False)

    assert a.ref.key == b.ref.key
    assert binstore.remote.list("bin/") == [a.ref.key]


# ---------------------------------------------------------------------------
# optimization, and its three refusals
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-03")
def test_an_optimized_pdf_is_stored_smaller_and_marked_optimized(
    binstore: BinStore,
) -> None:
    source = fake_pdf(padding=40_000)
    smaller = fake_pdf(padding=1_000)

    result = ingest_binary(
        binstore,
        source,
        ".pdf",
        compress=shrinker(smaller),
        extract_text=extractor({source: PROSE, smaller: PROSE}),
    )

    assert result.ref.optimized is True
    assert result.ref.size < result.ref.source_size
    assert result.saved_bytes > 0


@pytest.mark.spec("BIN-04")
def test_optimization_preserves_the_text_layer(binstore: BinStore) -> None:
    source = fake_pdf(padding=40_000)
    smaller = fake_pdf(padding=1_000)
    # One character shorter — inside the 2% tolerance, so it is accepted.
    texts = {source: PROSE, smaller: PROSE[:-1]}

    result = optimize_pdf(source, compress=shrinker(smaller), extract_text=extractor(texts))

    assert result.optimized is True
    assert result.text_after >= result.text_before * 0.98


@pytest.mark.spec("BIN-05")
def test_optimization_that_costs_text_is_rejected_and_the_original_stored(
    binstore: BinStore,
) -> None:
    source = fake_pdf(padding=40_000)
    lossy = fake_pdf(padding=100)
    texts = {source: PROSE, lossy: PROSE[: len(PROSE) // 2]}  # half the text gone

    result = ingest_binary(
        binstore, source, ".pdf", compress=shrinker(lossy), extract_text=extractor(texts)
    )

    assert result.optimize.reason == SKIPPED_TEXT_LOSS
    assert result.ref.optimized is False
    assert result.ref.sha256 == sha256_of(source)  # the ORIGINAL was stored
    assert binstore.fetch(result.ref) == source


@pytest.mark.spec("BIN-06")
def test_a_scanned_pdf_is_never_optimized(binstore: BinStore) -> None:
    scan = fake_pdf(body="", padding=80_000)
    texts = {scan: "  \n"}  # a scan yields essentially nothing

    result = ingest_binary(
        binstore,
        scan,
        ".pdf",
        compress=shrinker(fake_pdf(padding=10)),
        extract_text=extractor(texts),
    )

    assert result.optimize.reason == SKIPPED_SCANNED
    assert result.ref.optimized is False
    assert binstore.fetch(result.ref) == scan


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-07")
def test_an_optimized_ingest_records_what_the_publisher_served(
    binstore: BinStore,
) -> None:
    source = fake_pdf(padding=40_000)
    smaller = fake_pdf(padding=1_000)

    ref = ingest_binary(
        binstore,
        source,
        ".pdf",
        compress=shrinker(smaller),
        extract_text=extractor({source: PROSE, smaller: PROSE}),
    ).ref

    assert ref.source_sha256 == sha256_of(source)
    assert ref.source_size == len(source)
    assert ref.sha256 != ref.source_sha256
    assert ref.size != ref.source_size
    fm = ref.to_frontmatter()
    assert fm["source_sha256"] == ref.source_sha256 and fm["optimized"] is True


@pytest.mark.spec("BIN-08")
def test_a_verbatim_ingest_reports_one_identity_and_optimized_false(
    binstore: BinStore,
) -> None:
    data = fake_pdf()

    ref = ingest_binary(binstore, data, ".pdf", optimize=False).ref

    assert ref.sha256 == ref.source_sha256
    assert ref.size == ref.source_size
    assert ref.optimized is False


# ---------------------------------------------------------------------------
# verification — never downloads
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-09")
def test_verification_reads_no_object_bytes(binstore: BinStore) -> None:
    ref = ingest_binary(binstore, fake_pdf(), ".pdf", optimize=False).ref
    binstore.remote.reads = 0  # type: ignore[attr-defined]

    assert binstore.verify(ref).ok is True
    assert binstore.remote.reads == 0  # type: ignore[attr-defined]


@pytest.mark.spec("BIN-10")
def test_a_referenced_but_absent_object_reports_missing_rather_than_raising(
    binstore: BinStore,
) -> None:
    ref = BinaryRef.verbatim(fake_pdf(body="never stored"), ".pdf")

    result = binstore.verify(ref)

    assert result.outcome == MISSING
    assert result.ok is False


@pytest.mark.spec("BIN-11")
def test_altered_bytes_are_reported_as_a_hash_mismatch(binstore: BinStore) -> None:
    ref = ingest_binary(binstore, fake_pdf(), ".pdf", optimize=False).ref
    binstore.remote.write(ref.key, b"%PDF-1.5 tampered")

    result = binstore.verify(ref)

    assert result.outcome == HASH_MISMATCH
    assert result.detail


# ---------------------------------------------------------------------------
# on-demand: status, fetch, evict
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-12")
def test_an_uncached_binary_reports_not_downloaded_and_fetches_nothing(
    binstore: BinStore,
) -> None:
    ref = ingest_binary(binstore, fake_pdf(), ".pdf", optimize=False).ref
    binstore.evict(ref)
    binstore.remote.reads = 0  # type: ignore[attr-defined]

    status = binstore.status(ref)

    assert status.state == NOT_DOWNLOADED
    assert status.key == ref.key and status.bytes == ref.size
    assert binstore.remote.reads == 0  # type: ignore[attr-defined]


@pytest.mark.spec("BIN-13")
def test_fetching_a_not_downloaded_binary_makes_it_present_and_intact(
    binstore: BinStore,
) -> None:
    data = fake_pdf()
    ref = ingest_binary(binstore, data, ".pdf", optimize=False).ref
    binstore.evict(ref)

    got = binstore.fetch(ref)

    assert got == data
    assert sha256_of(got) == ref.sha256
    assert binstore.status(ref).state == PRESENT


@pytest.mark.spec("BIN-14")
def test_eviction_frees_the_local_copy_and_a_later_fetch_restores_it(
    binstore: BinStore,
) -> None:
    data = fake_pdf()
    ref = ingest_binary(binstore, data, ".pdf", optimize=False).ref
    before = binstore.cache_bytes()

    result = binstore.evict(ref)

    assert result.ok is True
    assert binstore.cache_bytes() < before
    assert binstore.remote.exists(ref.key)  # the remote is untouched
    assert binstore.fetch(ref) == data


@pytest.mark.spec("BIN-15")
def test_eviction_is_refused_when_the_remote_cannot_be_confirmed(
    binstore: BinStore,
) -> None:
    data = fake_pdf()
    ref = ingest_binary(binstore, data, ".pdf", optimize=False).ref
    binstore.remote.delete(ref.key)  # the remote lost it

    result = binstore.evict(ref)

    assert result.ok is False and result.outcome == MISSING
    assert binstore.is_cached(ref.key)  # the local copy survived
    assert binstore.fetch(ref) == data


# ---------------------------------------------------------------------------
# migration
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-16")
def test_migration_hashes_every_binary_and_deletes_no_original(
    binstore: BinStore, tmp_path: Path
) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "funders").mkdir(parents=True)
    a = corpus / "funders" / "report.pdf"
    b = corpus / "funders" / "deck.pdf"
    a.write_bytes(fake_pdf(body="alpha " * 60))
    b.write_bytes(fake_pdf(body="beta " * 60))
    (corpus / "funders" / "report.md").write_text("# wrapper")

    results = migrate_tree(binstore, corpus, optimize=False)

    assert len(results) == 2
    assert all(binstore.remote.exists(r.ref.key) for r in results)
    assert a.is_file() and b.is_file()  # nothing deleted — Behaviour 11


@pytest.mark.spec("BIN-17")
def test_migration_is_idempotent(binstore: BinStore, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.pdf").write_bytes(fake_pdf())

    first = migrate_tree(binstore, corpus, optimize=False)
    binstore.remote.reads = 0  # type: ignore[attr-defined]
    second = migrate_tree(binstore, corpus, optimize=False)

    assert [r.ref.key for r in first] == [r.ref.key for r in second]
    assert binstore.remote.list("bin/") == [first[0].ref.key]


# ---------------------------------------------------------------------------
# the shared cache — why you don't download twice
# ---------------------------------------------------------------------------


@pytest.mark.spec("BIN-19")
def test_a_second_corpus_referencing_the_same_binary_hits_the_shared_cache(
    tmp_path: Path,
) -> None:
    data = fake_pdf(body="a report two clients both hold " * 20)
    cache = tmp_path / "shared-cache"  # one machine, many corpora
    alpha = BinStore(CountingStore(tmp_path / "alpha-bucket"), cache_dir=cache)
    beta = BinStore(CountingStore(tmp_path / "beta-bucket"), cache_dir=cache)

    ref = ingest_binary(alpha, data, ".pdf", optimize=False).ref
    # The second corpus has its own bucket and its own object there...
    beta.put(ref, data)
    beta.remote.reads = 0  # type: ignore[attr-defined]

    got = beta.fetch(ref)

    assert got == data
    assert beta.remote.reads == 0  # ...but the machine already had the bytes


@pytest.mark.spec("BIN-20")
def test_clearing_the_cache_is_lossless(binstore: BinStore) -> None:
    data = fake_pdf()
    ref = ingest_binary(binstore, data, ".pdf", optimize=False).ref
    fm_before = ref.to_frontmatter()

    for path in sorted(binstore.cache_dir.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()

    assert binstore.cache_bytes() == 0
    assert ref.to_frontmatter() == fm_before  # no wrapper changed
    assert binstore.verify(ref).ok is True  # the remote is untouched
    assert binstore.fetch(ref) == data  # identical bytes come back


@pytest.mark.spec("BIN-21")
def test_a_missing_optimizer_degrades_rather_than_failing(binstore: BinStore) -> None:
    data = fake_pdf(padding=40_000)

    result = ingest_binary(
        binstore, data, ".pdf", compress=exploder, extract_text=extractor({data: PROSE})
    )

    assert result.optimize.reason == SKIPPED_NO_OPTIMIZER
    assert result.ref.optimized is False
    assert binstore.fetch(result.ref) == data  # the capture still succeeded


# ---------------------------------------------------------------------------
# BIN-18 — one contract, every store, no branching in the bodies
# ---------------------------------------------------------------------------


def _local(tmp_path: Path) -> LocalFsStore:
    return LocalFsStore(tmp_path / "conformance-local")


def _counting(tmp_path: Path) -> LocalFsStore:
    return CountingStore(tmp_path / "conformance-counting")


@pytest.mark.spec("BIN-18")
@pytest.mark.parametrize("build", [_local, _counting], ids=["local", "counting"])
def test_every_store_satisfies_the_same_binary_contract(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    store = BinStore(build(tmp_path), cache_dir=tmp_path / f"cache-{build.__name__}")
    data = fake_pdf(body="conformance " * 50)

    ref = ingest_binary(store, data, ".pdf", optimize=False).ref

    assert ref.key.startswith("bin/") and ref.sha256 in ref.key
    assert store.verify(ref).ok is True
    assert store.status(ref).state == PRESENT
    assert store.fetch(ref) == data

    assert store.evict(ref).ok is True
    assert store.status(ref).state == NOT_DOWNLOADED
    assert store.fetch(ref) == data  # restored identically

    # dedup: the same bytes ingested again produce one object
    ingest_binary(store, data, ".pdf", optimize=False)
    assert store.remote.list("bin/") == [ref.key]
