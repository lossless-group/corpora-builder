"""Tests for the browse surface — spec: context-v/specs/Browse-Corpus.md.

Against the pure functions in `src.server.browse`, not a running server. The
behaviour worth protecting is what the screen shows, and that is decided here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.server.browse import list_sources, load_source
from src.store import LocalFsStore


def _source(title: str, fetched: str, excerpt: str = "", status: str = "candidate") -> bytes:
    return (
        f"---\n"
        f"url: https://example.org/{title.lower().replace(' ', '-')}\n"
        f"title: {title}\n"
        f"fetched_at: '{fetched}'\n"
        f"status: {status}\n"
        f"published_at: '2025-03-01'\n"
        f"excerpt: {excerpt or 'An excerpt.'}\n"
        f"---\n\nbody\n"
    ).encode()


@pytest.fixture
def store(tmp_path: Path) -> LocalFsStore:
    s = LocalFsStore(tmp_path)
    s.write(
        "live/thesis/ocean/sources/2026-08-01_alpha.md", _source("Alpha", "2026-08-01T00:00:00Z")
    )
    s.write(
        "live/thesis/ocean/sources/2026-08-03_beta.md",
        _source("Beta", "2026-08-03T00:00:00Z", excerpt="Mentions DESALINATION here."),
    )
    s.write(
        "live/topic/solar/sources/2026-08-02_gamma.md", _source("Gamma", "2026-08-02T00:00:00Z")
    )
    return s


@pytest.mark.spec("BROWSE-01")
def test_listing_carries_the_display_fields(store: LocalFsStore) -> None:
    listing = list_sources(store)

    row = next(r for r in listing.rows if r.title == "Alpha")
    assert row.path.endswith("2026-08-01_alpha.md")
    assert row.status == "candidate"
    assert row.content_pulled is False
    assert row.published_at == "2025-03-01"
    assert row.excerpt
    assert row.domain == "thesis/ocean"
    assert listing.total == 3


@pytest.mark.spec("BROWSE-02")
def test_listing_filters_by_domain_prefix(store: LocalFsStore) -> None:
    listing = list_sources(store, prefix="live/thesis/ocean/")

    assert {r.title for r in listing.rows} == {"Alpha", "Beta"}


@pytest.mark.spec("BROWSE-03")
def test_a_damaged_file_appears_with_its_error(store: LocalFsStore) -> None:
    """13 sources once vanished from a count. A tidy-looking listing is worse."""
    store.write(
        "live/thesis/ocean/sources/2026-08-04_broken.md",
        b"---\nurl: https://example.org/x\n---\ntitle: Stranded\npublisher: Someone\n",
    )

    listing = list_sources(store)

    broken = next(r for r in listing.rows if "broken" in r.path)
    assert "StrandedContent" in broken.error
    assert listing.total == 4


@pytest.mark.spec("BROWSE-04")
def test_search_matches_title_and_excerpt_case_insensitively(store: LocalFsStore) -> None:
    by_title = list_sources(store, search="alpha")
    by_excerpt = list_sources(store, search="desalination")

    assert [r.title for r in by_title.rows] == ["Alpha"]
    assert [r.title for r in by_excerpt.rows] == ["Beta"]


@pytest.mark.spec("BROWSE-05")
def test_listing_is_newest_fetch_first(store: LocalFsStore) -> None:
    listing = list_sources(store)

    assert [r.title for r in listing.rows] == ["Beta", "Gamma", "Alpha"]


@pytest.mark.spec("BROWSE-06")
def test_loading_one_source_returns_it_unmodified(store: LocalFsStore) -> None:
    path = "live/thesis/ocean/sources/2026-08-01_alpha.md"

    assert load_source(store, path).encode() == store.read(path)


@pytest.mark.spec("BROWSE-07")
def test_a_traversing_path_is_refused(store: LocalFsStore) -> None:
    for bad in ("../../etc/passwd", "/etc/passwd", "live/../../secrets"):
        with pytest.raises(ValueError):
            load_source(store, bad)


@pytest.mark.spec("BROWSE-08")
def test_excerpt_falls_back_to_body_prose(store: LocalFsStore) -> None:
    """reach-edu's 845 files predate the excerpt field entirely."""
    store.write(
        "live/thesis/ocean/sources/2026-08-05_delta.md",
        b"---\nurl: https://example.org/d\ntitle: Delta\n"
        b"fetched_at: '2026-08-05T00:00:00Z'\n---\n\n"
        b"[Skip to content](https://x.com)\n\n*   [Nav](https://x.com)\n\n"
        b"The substantive opening sentence of the article, which is what a "
        b"reader actually wants to see on a card.\n",
    )

    row = next(r for r in list_sources(store).rows if r.title == "Delta")

    assert row.excerpt.startswith("The substantive opening sentence")
    assert "Skip to content" not in row.excerpt


@pytest.mark.spec("BROWSE-09")
def test_domain_handles_both_corpus_layouts(store: LocalFsStore) -> None:
    """corpora-builder writes live/<type>/<slug>/sources/; reach-edu predates it."""
    store.write("funders/annie-e-casey/2026-08-06_a.md", _source("A", "2026-08-06T00:00:00Z"))
    store.write(
        "strategies/workforce/sources/2026-08-07_b.md", _source("B", "2026-08-07T00:00:00Z")
    )

    domains = {r.title: r.domain for r in list_sources(store).rows}

    assert domains["A"] == "funders/annie-e-casey"
    assert domains["B"] == "strategies/workforce"


# ---------------------------------------------------------------------------
# Opening the app must not read the whole corpus
# ---------------------------------------------------------------------------


class CountingStore(LocalFsStore):
    """Counts body reads, so "does this open the file" is an assertion."""

    def __init__(self, root) -> None:  # type: ignore[no-untyped-def]
        super().__init__(root)
        self.reads = 0

    def read(self, key: str) -> bytes:
        self.reads += 1
        return super().read(key)


def _many(store: LocalFsStore, n: int) -> None:
    for i in range(n):
        body = (
            f'---\ntitle: "Source {i}"\n' "fetched_at: 2026-08-01T00:00:00Z\n" f"---\n\nBody {i}.\n"
        )
        store.write(
            f"live/topics/t{i % 3}/sources/2026-08-{(i % 28) + 1:02d}_source-{i:03d}.md",
            body.encode(),
        )


@pytest.mark.spec("BROWSE-14")
def test_meta_derives_count_and_domains_without_reading_any_file(tmp_path: Path) -> None:
    """Reading all 845 sources to answer this took 20.6s cold against R2, which
    is what a window stuck on 'Starting the backend…' actually was."""
    from src.server.browse import list_domains

    store = CountingStore(tmp_path / "c")
    _many(store, 40)
    store.reads = 0

    total, domains = list_domains(store)

    assert total == 40
    assert len(domains) == 3
    assert store.reads == 0


@pytest.mark.spec("BROWSE-15")
def test_an_unsearched_page_reads_only_that_page(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "c")
    _many(store, 40)
    store.reads = 0

    listing = list_sources(store, limit=10)

    assert len(listing.rows) == 10
    assert listing.total == 40  # the count is still honest
    assert store.reads == 10  # ...but only ten files were opened


@pytest.mark.spec("BROWSE-15")
def test_a_search_still_reads_everything_because_it_has_to(tmp_path: Path) -> None:
    store = CountingStore(tmp_path / "c")
    _many(store, 40)
    store.reads = 0

    list_sources(store, search="Source 7", limit=10)

    assert store.reads == 40


@pytest.mark.spec("BROWSE-16")
def test_filtering_by_domain_is_independent_of_the_storage_layout(tmp_path: Path) -> None:
    """Two layouts exist in the wild and a domain name belongs to neither.

    The browser used to send `<domain>/` as a key prefix. That matches
    reach-edu's flat `<type>/<slug>/` corpus and silently matches NOTHING in a
    corpus this tool wrote, where the same domain lives at
    `live/<type>/<slug>/sources/`. A filter that returns zero rows for a folder
    that plainly has sources in it is the failure this project exists against.
    """
    store = LocalFsStore(tmp_path / "corpus")
    wrapper = '---\ntitle: "T"\nurl: "https://e.org/a"\n---\n\nBody.\n'
    store.write("topics/future-of-work/2026-01-01_flat.md", wrapper.encode())
    store.write("live/topics/future-of-work/sources/2026-01-02_nested.md", wrapper.encode())
    store.write("topics/other/2026-01-03_elsewhere.md", wrapper.encode())

    listing = list_sources(store, domain="topics/future-of-work")

    assert listing.total == 2
    assert {r.path.rsplit("/", 1)[-1] for r in listing.rows} == {
        "2026-01-01_flat.md",
        "2026-01-02_nested.md",
    }


@pytest.mark.spec("BROWSE-18")
def test_a_domain_filter_ending_in_a_slash_widens_instead_of_emptying(tmp_path: Path) -> None:
    """`funders/` is a legal filter value, not a malformed one.

    The domain combobox's segment-wise Backspace walks
    `funders/ascendium-education` -> `funders/` -> `''`, and the middle step is
    the whole point of that walk: show me this parent. Compared literally it
    matched nothing — `funders/` never equals a domain, and `funders//` is never
    a prefix of one — so widening a filter silently returned zero rows.

    Two features that were each correct alone, wrong at the seam. Found by
    driving the running app, which is the only place the two ever met.
    """
    store = LocalFsStore(tmp_path / "corpus")
    wrapper = '---\ntitle: "T"\nurl: "https://e.org/a"\n---\n\nBody.\n'
    store.write("live/funders/ascendium-education/sources/2026-01-01_a.md", wrapper.encode())
    store.write("live/funders/ballmer-group/sources/2026-01-02_b.md", wrapper.encode())
    store.write("live/strategies/workforce-development/sources/2026-01-03_c.md", wrapper.encode())

    widened = list_sources(store, domain="funders/")
    exact = list_sources(store, domain="funders/ascendium-education")

    assert widened.total == 2, "widening to the parent must show the parent's sources"
    assert exact.total == 1
    # And an all-slash value is the same as no filter, not a filter matching nothing.
    assert list_sources(store, domain="/").total == 3

    # `corpus_total` counts before ANY narrowing — domain included. Measured
    # after the domain filter it reports "2 of 2", which is a number that has
    # stopped being an answer.
    assert widened.corpus_total == 3
    assert exact.corpus_total == 3
