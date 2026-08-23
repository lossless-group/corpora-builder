"""Tests for link-first capture — spec: context-v/specs/Capture-Link-First.md.

No network. `FakeFetcher` returns whatever a test asks it to, including
failures, because the interesting cases are the ones a live fetch will not
reliably produce on demand — a 404, a PDF, a body longer than the excerpt cap.

The live counterpart is gated behind `CORPORA_LIVE_FETCH=1` and run by hand,
like every other real-world leg in this repo. Mocked HTTP proves the code shape
and says nothing about what Jina returns for a real page.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.binary.store import BinStore
from src.capture import EXCERPT_CHARS, FetchResult, add_source
from src.model import SourceFile
from src.store import LocalFsStore

NOW = "2026-08-08T12:00:00Z"
TODAY = "2026-08-08"


class FakeFetcher:
    """Returns a scripted `FetchResult`, and records what it was asked for."""

    def __init__(self, result: FetchResult) -> None:
        self.result = result
        self.calls: list[tuple[str, bool]] = []

    def fetch(self, url: str, full: bool = False) -> FetchResult:
        self.calls.append((url, full))
        return self.result


def _ok(body: str = "Body text.", **kw: object) -> FetchResult:
    defaults = {
        "ok": True,
        "status": "HTTP 200 (body verified)",
        "title": "Ocean Energy Report",
        "publisher": "IEA-OES",
        "published_at": "2025-03-01",
        "body": body,
        "content_type": "text/html",
    }
    defaults.update(kw)
    return FetchResult(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def store(tmp_path: Path) -> LocalFsStore:
    return LocalFsStore(tmp_path)


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


@pytest.mark.spec("CAPTURE-01")
def test_add_writes_a_source_file_under_its_domain(store: LocalFsStore) -> None:
    result = add_source(
        store,
        "https://example.org/ocean",
        FakeFetcher(_ok()),
        domain="thesis/ocean-energy",
        now=NOW,
    )

    assert result.created
    assert result.path == (f"live/thesis/ocean-energy/sources/{TODAY}_ocean-energy-report.md")

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.url == "https://example.org/ocean"
    assert written.fetched_at == NOW
    assert written.status == "candidate"


@pytest.mark.spec("CAPTURE-06")
def test_no_domain_lands_in_the_inbox(store: LocalFsStore) -> None:
    """The inbox is capture-first staging, and the richest bucket."""
    result = add_source(store, "https://example.org/a", FakeFetcher(_ok()), now=NOW)

    assert result.path.startswith("live/inbox/")


@pytest.mark.spec("CAPTURE-13")
def test_origin_and_fetched_at_are_recorded(store: LocalFsStore) -> None:
    result = add_source(
        store, "https://example.org/a", FakeFetcher(_ok()), origin="searxng", now=NOW
    )

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.origin == "searxng"
    assert written.fetched_at == NOW


# ---------------------------------------------------------------------------
# The two-tier gate
# ---------------------------------------------------------------------------


@pytest.mark.spec("CAPTURE-04")
def test_a_bare_add_stores_metadata_only(store: LocalFsStore) -> None:
    """Grounding cost is spent on survivors, never on candidates."""
    long_body = "x" * (EXCERPT_CHARS * 5)
    fetcher = FakeFetcher(_ok(body=long_body))

    result = add_source(store, "https://example.org/a", fetcher, now=NOW)

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.content_pulled is False
    assert long_body not in written.body
    assert fetcher.calls == [("https://example.org/a", False)]


@pytest.mark.spec("CAPTURE-05")
def test_fetch_pulls_the_full_body(store: LocalFsStore) -> None:
    body = "The full article text, all of it.\n" * 20
    fetcher = FakeFetcher(_ok(body=body))

    result = add_source(store, "https://example.org/a", fetcher, full=True, now=NOW)

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.content_pulled is True
    assert body.strip() in written.body
    assert fetcher.calls == [("https://example.org/a", True)]


@pytest.mark.spec("CAPTURE-11")
def test_excerpt_is_capped(store: LocalFsStore) -> None:
    result = add_source(store, "https://example.org/a", FakeFetcher(_ok(body="y" * 1000)), now=NOW)

    written = SourceFile.parse(store.read(result.path).decode())
    assert 0 < len(written.excerpt) <= EXCERPT_CHARS + 1  # +1 for an ellipsis


# ---------------------------------------------------------------------------
# Dedup, collisions, and failures
# ---------------------------------------------------------------------------


@pytest.mark.spec("CAPTURE-02")
def test_a_duplicate_normalised_url_writes_nothing(store: LocalFsStore) -> None:
    first = add_source(
        store, "https://www.example.org/a/", FakeFetcher(_ok()), domain="topic/x", now=NOW
    )

    second = add_source(
        store,
        "http://example.org/a?utm_source=twitter",  # same resource, cosmetic differences
        FakeFetcher(_ok()),
        domain="topic/x",
        now=NOW,
    )

    assert second.created is False
    assert second.duplicate_of == first.path
    assert len(store.list("live/topic/x/")) == 1


@pytest.mark.spec("CAPTURE-08")
def test_normalized_url_is_canonical_while_url_is_verbatim(store: LocalFsStore) -> None:
    raw = "https://www.Example.org/a/?utm_source=x#frag"

    result = add_source(store, raw, FakeFetcher(_ok()), now=NOW)

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.url == raw
    assert written.normalized_url == "example.org/a"


@pytest.mark.spec("CAPTURE-12")
def test_a_name_collision_from_a_different_url_gets_a_suffix(store: LocalFsStore) -> None:
    add_source(store, "https://example.org/one", FakeFetcher(_ok()), domain="topic/x", now=NOW)

    second = add_source(
        store, "https://example.org/two", FakeFetcher(_ok()), domain="topic/x", now=NOW
    )

    assert second.created
    assert second.path.endswith("_2.md")
    assert len(store.list("live/topic/x/")) == 2


@pytest.mark.spec("CAPTURE-03")
def test_an_unreachable_url_still_produces_a_file(store: LocalFsStore) -> None:
    """A source that 404s is how you learn a citation rotted."""
    failed = FetchResult(ok=False, status="HTTP 404 (not found)")

    result = add_source(store, "https://example.org/gone", FakeFetcher(failed), now=NOW)

    assert result.created
    written = SourceFile.parse(store.read(result.path).decode())
    assert written.machine_verdict == "HTTP 404 (not found)"
    assert written.content_pulled is False


@pytest.mark.spec("CAPTURE-07")
def test_capture_never_writes_an_analyst_verdict(store: LocalFsStore) -> None:
    """Reachability is not approval — permanently, on every path."""
    for fetch_result in (_ok(), FetchResult(ok=False, status="HTTP 500")):
        result = add_source(
            store, f"https://example.org/{fetch_result.ok}", FakeFetcher(fetch_result), now=NOW
        )
        written = SourceFile.parse(store.read(result.path).decode())

        assert written.verdict == ""
        assert written.machine_verdict != ""


# ---------------------------------------------------------------------------
# Binaries — filed into bin/, pointed at from the markdown
#
# `CAPTURE-09` is retired: binaries used to land as a sibling beside their
# markdown, which is what made them 90.5% of the corpus bytes and forced Git LFS.
# They now live once, addressed by content hash. See Binary-Ingest-And-Bin-Store.
# ---------------------------------------------------------------------------


@pytest.mark.spec("CAPTURE-17")
def test_a_pdf_is_filed_into_bin_and_pointed_at_not_copied_beside(
    store: LocalFsStore, tmp_path: Path
) -> None:
    pdf = b"%PDF-1.7\x00 fake bytes"
    fetcher = FakeFetcher(_ok(content_type="application/pdf", raw=pdf, body=""))
    bin_store = BinStore(store, cache_dir=tmp_path / "cache")

    result = add_source(
        store,
        "https://example.org/report.pdf",
        fetcher,
        domain="topic/x",
        now=NOW,
        bin_store=bin_store,
    )

    asset = SourceFile.parse(store.read(result.path).decode()).binary_asset
    assert asset is not None
    assert asset.download_status == "ok"

    # the pointer, not a path beside the markdown
    assert asset.binary_key.startswith("bin/")
    assert asset.sha256 in asset.binary_key
    assert store.read(asset.binary_key) == pdf

    # provenance: sha256/size_bytes keep meaning the publisher's file
    assert asset.sha256 == hashlib.sha256(pdf).hexdigest()
    assert asset.size_bytes == len(pdf)
    assert asset.optimized is False
    assert asset.optimized_sha256 == "" and asset.optimized_bytes == 0

    # and emphatically NOT beside the markdown
    assert result.path[: -len(".md")] + ".pdf" not in store.list("")


@pytest.mark.spec("CAPTURE-18")
def test_the_same_pdf_in_two_domains_is_one_object(store: LocalFsStore, tmp_path: Path) -> None:
    pdf = b"%PDF-1.7\x00 a report two domains both want"
    bin_store = BinStore(store, cache_dir=tmp_path / "cache")

    paths = [
        add_source(
            store,
            f"https://example.org/{n}/report.pdf",
            FakeFetcher(_ok(content_type="application/pdf", raw=pdf, body="")),
            domain=d,
            now=NOW,
            bin_store=bin_store,
        ).path
        for n, d in (("a", "topic/alpha"), ("b", "topic/beta"))
    ]

    assets = [SourceFile.parse(store.read(p).decode()).binary_asset for p in paths]
    assert assets[0] is not None and assets[1] is not None
    assert assets[0].binary_key == assets[1].binary_key
    assert len(store.list("bin/")) == 1


@pytest.mark.spec("CAPTURE-10")
def test_a_failed_pdf_download_is_still_recorded(store: LocalFsStore) -> None:
    """Absence cannot distinguish 'never tried' from 'tried and got a 403'."""
    failed = FetchResult(ok=False, status="HTTP 403 (forbidden)", content_type="application/pdf")

    result = add_source(
        store, "https://example.org/report.pdf", FakeFetcher(failed), domain="topic/x", now=NOW
    )

    written = SourceFile.parse(store.read(result.path).decode())
    assert written.binary_asset is not None
    assert written.binary_asset.download_status != "ok"
    assert not store.exists(result.path[: -len(".md")] + ".pdf")


# ---------------------------------------------------------------------------
# Jina's actual response shape
# ---------------------------------------------------------------------------

JINA_RESPONSE = """Title: Introducing Claude Opus 4.5

URL Source: https://www.anthropic.com/news/claude-opus-4-5

Markdown Content:
[Skip to main content](https://example.com#main)[Skip to footer](https://x.com)

[](https://www.anthropic.com/)

*   [Research](https://www.anthropic.com/research)
*   [Policy](https://www.anthropic.com/policy)

Today we are releasing our most capable model, which sets a new standard for
coding and agentic reasoning across the industry.
"""


@pytest.mark.spec("CAPTURE-14")
def test_jina_preamble_is_separated_from_the_body() -> None:
    """The preamble is blank-line separated, so 'stop at the first blank' finds
    only the title — the bug that put 'URL Source: …' in the first excerpt."""
    from src.capture.fetch import parse_jina_preamble

    preamble, body = parse_jina_preamble(JINA_RESPONSE)

    assert preamble["Title"] == "Introducing Claude Opus 4.5"
    assert "URL Source" in preamble
    assert not body.startswith("Markdown Content")
    assert "Skip to main content" in body


@pytest.mark.spec("CAPTURE-15")
def test_excerpt_skips_navigation_chrome() -> None:
    """An excerpt reading 'Skip to main content' teaches analysts to ignore
    excerpts."""
    from src.capture.fetch import parse_jina_preamble, prose_excerpt

    _, body = parse_jina_preamble(JINA_RESPONSE)
    excerpt = prose_excerpt(body, EXCERPT_CHARS)

    assert excerpt.startswith("Today we are releasing")
    assert "Skip to" not in excerpt
    assert "](" not in excerpt


@pytest.mark.spec("CAPTURE-16")
def test_a_new_source_states_its_own_status(store: LocalFsStore) -> None:
    """A fresh file omitting `status: candidate` is not stating its lifecycle."""
    result = add_source(store, "https://example.org/a", FakeFetcher(_ok()), now=NOW)

    raw = store.read(result.path).decode()
    assert "status: candidate" in raw
    assert "content_pulled: false" in raw
