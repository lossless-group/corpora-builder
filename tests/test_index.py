"""Covers `context-v/specs/Search-Index.md`.

The manifest exists for one measured reason: a search opened every file in the
corpus — 845 round-trips and up to 5.8 seconds against reach-edu — because the
four strings it matches on live inside those files.

**These tests assert read counts, never elapsed time.** A wall-clock promise
passes on a fast laptop and rots quietly; a read count is what "does this open
the file" actually means. Same discipline as `BROWSE-14`, `BROWSE-15` and the
corpus tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.binary.keys import BinaryRef
from src.binary.store import BinStore
from src.capture import FetchResult, add_source
from src.index.manifest import MANIFEST_KEY, Manifest, load_manifest, save_manifest
from src.server.browse import build_manifest, list_sources
from src.server.tree import build_tree, visible_keys
from src.store import LocalFsStore

WRAPPER = """---
title: "{title}"
url: "https://example.org/{slug}"
normalized_url: "example.org/{slug}"
fetched_at: "{fetched}"
status: "fetched"
content_pulled: true
{domains}---

{body}
"""

BODY = (
    "A substantial paragraph of real prose about the funding landscape and the "
    "programs that pay for it in rural counties."
)


class CountingStore(LocalFsStore):
    """Counts body reads, so "does this open the file" is an assertion."""

    def __init__(self, root) -> None:  # type: ignore[no-untyped-def]
        super().__init__(root)
        self.reads = 0

    def read(self, key: str) -> bytes:
        self.reads += 1
        return super().read(key)


def _domains(*values: str) -> str:
    if not values:
        return ""
    return "domains:\n" + "".join(f'  - "{v}"\n' for v in values)


def _put(
    store: LocalFsStore, key: str, title: str, when: str, *doms: str, body: str = BODY
) -> None:
    store.write(
        key,
        WRAPPER.format(
            title=title,
            slug=title.lower().replace(" ", "-"),
            fetched=when,
            domains=_domains(*doms),
            body=body,
        ).encode(),
    )


@pytest.fixture()
def store(tmp_path: Path) -> CountingStore:
    """Six sources, one of them tagged into a strategy it does not live under."""
    s = CountingStore(tmp_path / "corpus")
    s.write(
        "live/strategies/workforce-development/index.md",
        b'---\ntype: "strategy"\nslug: "workforce-development"\ntitle: "Workforce Development"\n'
        b"---\n\nThe case.\n",
    )
    _put(
        s,
        "live/strategies/workforce-development/sources/2026-01-01_a.md",
        "Apprenticeship Report",
        "2026-01-01T00:00:00Z",
        "strategy:workforce-development",
    )
    _put(
        s,
        "live/strategies/workforce-development/sources/2026-01-02_b.md",
        "Skills Gap Study",
        "2026-01-02T00:00:00Z",
        "strategy:workforce-development",
    )
    _put(s, "live/funders/gates/2026-09-01_c.md", "Grant Announcement", "2026-09-01T00:00:00Z")
    _put(s, "live/funders/gates/2026-09-02_d.md", "Portfolio Update", "2026-09-02T00:00:00Z")
    # Tagged into a strategy whose folder it does not live in. Before the
    # manifest this was reachable only under search — see FOCUS-07.
    _put(
        s,
        "live/funders/gates/2026-01-05_x.md",
        "Cross-Tagged Brief",
        "2026-01-05T00:00:00Z",
        "strategy:workforce-development",
    )
    return s


def _index(s: LocalFsStore) -> bytes:
    return save_manifest(s, build_manifest(s))


# ---------------------------------------------------------------------------
# the point of the whole thing
# ---------------------------------------------------------------------------


@pytest.mark.spec("INDEX-01")
def test_an_indexed_search_reads_only_the_manifest(store: CountingStore) -> None:
    """The measured claim: 845 reads become one.

    Asserted as an exact count rather than "fast", because 845 sequential GETs
    against R2 is 5.8 seconds on a bad connection and 1.2 on a good one, and
    neither number is the promise.
    """
    _index(store)
    store.reads = 0

    hits = list_sources(store, search="apprenticeship")

    assert [r.title for r in hits.rows] == ["Apprenticeship Report"]
    assert store.reads == 1
    assert not hits.index_stale


@pytest.mark.spec("INDEX-01")
def test_an_indexed_page_load_reads_only_the_manifest(store: CountingStore) -> None:
    _index(store)
    store.reads = 0

    listing = list_sources(store, limit=2)

    assert len(listing.rows) == 2
    assert listing.total == 5  # index.md is not a source
    assert store.reads == 1


# ---------------------------------------------------------------------------
# what must survive being written down
# ---------------------------------------------------------------------------


@pytest.mark.spec("INDEX-02")
def test_a_damaged_file_is_indexed_with_its_error(store: CountingStore) -> None:
    """The ImmuneCo rule, carried into the index.

    13 sources were once silently absent from a count. An index that quietly
    omits what it could not parse reproduces exactly that, with a speedup
    attached — so a damaged file gets an entry and the entry carries the error.
    """
    store.write(
        "live/funders/gates/2026-09-03_broken.md",
        b"---\nurl: https://example.org/x\n---\ntitle: Stranded\npublisher: Someone\n",
    )
    _index(store)
    store.reads = 0

    listing = list_sources(store)

    broken = [r for r in listing.rows if r.path.endswith("_broken.md")]
    assert len(broken) == 1, "a file that will not parse must still be listed"
    assert "StrandedContent" in broken[0].error, "and it must say why"
    assert broken[0].title == "2026-09-03_broken.md"  # the filename, as a direct read renders it
    assert store.reads == 1  # ...and it did not have to be re-opened to find that out


@pytest.mark.spec("INDEX-07")
def test_indexed_and_unindexed_listings_are_identical(store: CountingStore) -> None:
    """Every field, both modes.

    The failure this guards against presents to a user as "search finds
    different things than the page does", which is very hard to diagnose and
    trivially prevented by comparing the two.
    """
    before_plain = list_sources(store)
    before_search = list_sources(store, search="apprenticeship")

    _index(store)

    after_plain = list_sources(store)
    after_search = list_sources(store, search="apprenticeship")

    assert [r.as_dict() for r in after_plain.rows] == [r.as_dict() for r in before_plain.rows]
    assert [r.as_dict() for r in after_search.rows] == [r.as_dict() for r in before_search.rows]
    assert after_plain.total == before_plain.total
    assert after_plain.corpus_total == before_plain.corpus_total


@pytest.mark.spec("INDEX-07")
def test_the_stored_excerpt_is_the_one_a_direct_read_computes(store: CountingStore) -> None:
    """reach-edu's 845 files carry no `excerpt:` — they predate the field — so a
    listing falls back to the body and search matches THAT. Storing anything
    else would silently change what search finds the day a corpus got indexed."""
    unindexed = {r.path: r.excerpt for r in list_sources(store).rows}
    _index(store)
    indexed = {r.path: r.excerpt for r in list_sources(store).rows}

    assert indexed == unindexed
    assert all(e for e in indexed.values()), "the fallback must actually have produced prose"


# ---------------------------------------------------------------------------
# staying current
# ---------------------------------------------------------------------------


@pytest.mark.spec("INDEX-03")
def test_capture_updates_one_entry_and_reads_no_source(store: CountingStore) -> None:
    """A capture that triggered a rebuild would cost more than the index saves.

    This also covers the duplicate check, which used to open every markdown file
    under the prefix on every single capture.
    """

    class FakeFetcher:
        def fetch(self, url: str, full: bool = False) -> FetchResult:
            return FetchResult(
                ok=True,
                status="HTTP 200",
                title="Newly Captured",
                body=BODY,
                content_type="text/html",
            )

    _index(store)
    before = load_manifest(store)
    assert before is not None
    store.reads = 0

    result = add_source(store, "https://example.org/new", FakeFetcher(), now="2026-10-01T00:00:00Z")
    # Counted here: reading the manifest back to check the assertions below is
    # this test's cost, not capture's.
    reads_during_capture = store.reads

    after = load_manifest(store)
    assert after is not None
    assert set(after.entries) - set(before.entries) == {result.path}
    assert after.entries[result.path].title == "Newly Captured"
    assert after.entries[result.path].normalized_url

    # One read: the manifest. No source file was opened — not for the duplicate
    # check, and not to rebuild.
    assert reads_during_capture == 1


@pytest.mark.spec("INDEX-04")
def test_keys_the_manifest_has_never_seen_are_read_and_reported(store: CountingStore) -> None:
    """Drift repairs itself incrementally: five captures behind costs five reads."""
    _index(store)
    _put(store, "live/funders/gates/2026-10-01_e.md", "Later Arrival", "2026-10-01T00:00:00Z")
    _put(store, "live/funders/gates/2026-10-02_f.md", "Later Still", "2026-10-02T00:00:00Z")
    store.reads = 0

    listing = list_sources(store)

    titles = [r.title for r in listing.rows]
    assert "Later Arrival" in titles and "Later Still" in titles
    assert listing.index_stale, "the listing has to say the index needs rebuilding"
    assert store.reads == 3  # the manifest, plus exactly the two it had not seen


@pytest.mark.spec("INDEX-04")
def test_a_key_removed_from_the_store_leaves_the_listing(store: CountingStore) -> None:
    _index(store)
    store.delete("live/funders/gates/2026-09-01_c.md")

    listing = list_sources(store)

    assert "Grant Announcement" not in [r.title for r in listing.rows]
    assert not listing.index_stale, "a deletion needs no rebuild — nothing was missed"


@pytest.mark.spec("INDEX-05")
def test_an_edit_in_place_is_the_case_a_key_comparison_cannot_see(store: CountingStore) -> None:
    """The named limit, asserted rather than hoped about.

    Same key, changed content: nothing in a key-set comparison can notice. The
    listing serves the older values until somebody reindexes. This test exists
    so the limit is documented in executable form — if a future `list_stat()`
    closes it, this test goes red and says so.
    """
    key = "live/funders/gates/2026-09-01_c.md"
    _index(store)
    _put(store, key, "Renamed Entirely", "2026-09-01T00:00:00Z")

    listing = list_sources(store)

    assert "Renamed Entirely" not in [r.title for r in listing.rows]
    assert "Grant Announcement" in [r.title for r in listing.rows]
    assert not listing.index_stale  # ...and it cannot even tell you it is wrong

    _index(store)
    assert "Renamed Entirely" in [r.title for r in list_sources(store).rows]


@pytest.mark.spec("INDEX-08")
def test_an_unindexed_corpus_behaves_exactly_as_before(store: CountingStore) -> None:
    """No manifest is a real answer, not an error. Whether a corpus is indexed
    stays an explicit `reindex`, so nothing that has never been indexed changes."""
    assert load_manifest(store) is None
    store.reads = 0

    listing = list_sources(store, limit=2)

    assert len(listing.rows) == 2
    assert not listing.index_stale
    assert store.reads == 2  # only the page — no speculative probe for a manifest


# ---------------------------------------------------------------------------
# what must NOT be written down
# ---------------------------------------------------------------------------


@pytest.mark.spec("INDEX-06")
def test_binary_presence_is_a_fact_about_this_machine(tmp_path: Path) -> None:
    """The manifest is shared; a download is not.

    Caching `binary_state` would have one laptop's downloads showing as
    `present` on a laptop that has never fetched the bytes — the same class of
    bug `BinStore`'s two-bucket test exists to catch.
    """
    s = LocalFsStore(tmp_path / "corpus")
    payload = b"%PDF-1.4 not really a pdf"
    ref = BinaryRef.verbatim(payload, ext=".pdf")
    s.write(ref.key, payload)
    s.write(
        "live/funders/gates/2026-01-01_pdf.md",
        (
            "---\n"
            'title: "A Report"\n'
            'url: "https://example.org/r.pdf"\n'
            'fetched_at: "2026-01-01T00:00:00Z"\n'
            "binary_asset:\n"
            '  filename: "r.pdf"\n'
            f'  binary_key: "{ref.key}"\n'
            "  size_bytes: 1234\n"
            "---\n\n" + BODY + "\n"
        ).encode(),
    )
    _index(s)

    downloaded = BinStore(remote=s, cache_dir=tmp_path / "machine-a")
    never = BinStore(remote=s, cache_dir=tmp_path / "machine-b")
    downloaded.fetch(ref)  # machine A has actually pulled the bytes
    assert downloaded.is_cached(ref.key) and not never.is_cached(ref.key)

    # ONE manifest, two machines, two different honest answers.
    on_a = list_sources(s, bin_store=downloaded).rows[0]
    on_b = list_sources(s, bin_store=never).rows[0]

    assert on_a.binary_key == on_b.binary_key == ref.key
    assert on_a.binary_state == "present"
    assert on_b.binary_state == "not_downloaded"

    # ...because the manifest never carried a state that could be believed.
    manifest = load_manifest(s)
    assert manifest is not None
    entry = next(e for e in manifest.entries.values() if e.binary_key)
    assert not hasattr(entry, "binary_state")
    assert entry.binary_key == ref.key


@pytest.mark.spec("INDEX-09")
def test_nothing_derived_is_a_source_or_appears_in_the_tree(store: CountingStore) -> None:
    """The blueprint's test is not "is this internal?" but "does this level tell
    the reader anything?" A derived cache does not.

    The manifest is `.jsonl`, so the listing's existing extension filter would
    exclude it whatever we did — which makes it a weak thing to assert alone.
    The promise is about the PREFIX: nothing under `index/` is a source, whatever
    it is named. A derived markdown document is the case that proves it, and the
    one a future summary or report would land in.
    """
    _index(store)
    store.write("index/notes.md", b'---\ntitle: "Derived Notes"\n---\n\n' + BODY.encode())

    listing = list_sources(store)
    paths = [r.path for r in listing.rows]
    assert MANIFEST_KEY not in paths
    assert "index/notes.md" not in paths, "the prefix decides, not the extension"
    assert "Derived Notes" not in [r.title for r in listing.rows]

    keys = store.list("")
    assert MANIFEST_KEY in keys and "index/notes.md" in keys, "...they are really there"
    assert visible_keys(keys) == [k for k in keys if not k.startswith("index/")]
    assert not any(n.name == "index" for n in build_tree(keys))


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


@pytest.mark.spec("INDEX-10")
def test_rebuilding_an_unchanged_corpus_is_byte_identical(store: CountingStore) -> None:
    """Which is why the manifest carries no timestamp.

    A `built_at` would make every rebuild differ, and the search bundle's
    staleness check — a hash of these very bytes — would report stale every time
    anybody reindexed.
    """
    first = _index(store)
    second = _index(store)

    assert first == second
    assert first, "and it is not trivially empty"


@pytest.mark.spec("INDEX-10")
def test_a_damaged_line_costs_one_source_not_the_manifest(store: CountingStore) -> None:
    blob = _index(store)
    lines = blob.decode().splitlines()
    store.write(MANIFEST_KEY, ("\n".join(["{not json at all"] + lines[1:]) + "\n").encode())

    manifest = load_manifest(store)

    assert manifest is not None
    assert len(manifest.entries) == len(lines) - 1


@pytest.mark.spec("INDEX-10")
def test_an_empty_corpus_round_trips(tmp_path: Path) -> None:
    s = LocalFsStore(tmp_path / "empty")
    manifest = Manifest()
    save_manifest(s, manifest)

    assert load_manifest(s) is not None
    assert load_manifest(s).entries == {}  # type: ignore[union-attr]
