"""Covers `context-v/specs/Strategy-Focus.md`.

**These tests once asserted the opposite.** The first reading of "mainly look
here" was emphasis — focus reorders, never excludes — and every test here checked
that the total came back unchanged. Driven in a real browser it was
indistinguishable from nothing happening: 200 rows on screen, 82 matches, so only
the top of the list moved and rows 83-200 were unrelated. The operator's report
was "the tags don't actually toggle the filtered search results," and they were
right.

Focus narrows. What preserves access to the rest of the corpus is that the toggle
is a toggle, and that `corpus_total` rides alongside `total` so a narrowed list
always says what it is a subset of.

`FOCUS-07` was inverted on 2026-08-23, when the index this spec had only named
actually shipped. The ID is unchanged and the row in the spec table was rewritten
rather than retired — the promise moved, it did not disappear.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.index.manifest import save_manifest
from src.server.browse import (
    build_manifest,
    list_domain_defs,
    list_sources,
)
from src.store import LocalFsStore

WRAPPER = """---
title: "{title}"
url: "https://example.org/{slug}"
fetched_at: "{fetched}"
status: "fetched"
content_pulled: true
{domains}---

Some body text about grants.
"""


def _domains(*values: str) -> str:
    if not values:
        return ""
    return "domains:\n" + "".join(f'  - "{v}"\n' for v in values)


@pytest.fixture()
def store(tmp_path: Path) -> LocalFsStore:
    """Three strategy sources, one topic source, and two untagged funder sources.

    Shaped like reach-edu: most of the corpus carries no `domains:` at all, and
    that is not a defect — an untagged source is not unclassified, it is just not
    the first place to look for any particular strategy.
    """
    s = LocalFsStore(tmp_path / "corpus")

    def define(folder: str, kind: str, slug: str, title: str) -> None:
        """A domain declares itself. Without this there is no focus to offer —
        the vocabulary is read from the corpus, never assumed."""
        s.write(
            f"live/{folder}/index.md",
            f'---\ntype: "{kind}"\nslug: "{slug}"\ntitle: "{title}"\n---\n\nThe case.\n'.encode(),
        )

    define(
        "strategies/workforce-development",
        "strategy",
        "workforce-development",
        "Workforce Development",
    )
    define(
        "strategies/adult-literacy-numeracy",
        "strategy",
        "adult-literacy-numeracy",
        "Adult Literacy",
    )
    define("topics/future-of-work", "topic", "future-of-work", "Future of Work")

    def put(key: str, title: str, fetched: str, *doms: str) -> None:
        s.write(
            key,
            WRAPPER.format(
                title=title,
                slug=title.lower().replace(" ", "-"),
                fetched=fetched,
                domains=_domains(*doms),
            ).encode(),
        )

    put(
        "live/strategies/workforce-development/sources/2026-01-01_a.md",
        "Apprenticeship Report",
        "2026-01-01T00:00:00Z",
        "strategy:workforce-development",
    )
    put(
        "live/strategies/workforce-development/sources/2026-01-02_b.md",
        "Skills Gap Study",
        "2026-01-02T00:00:00Z",
        "strategy:workforce-development",
    )
    put(
        "live/strategies/adult-literacy-numeracy/sources/2026-02-01_c.md",
        "Reading Levels",
        "2026-02-01T00:00:00Z",
        "strategy:adult-literacy-numeracy",
    )
    put(
        "live/topics/future-of-work/sources/2026-03-01_d.md",
        "Automation Outlook",
        "2026-03-01T00:00:00Z",
        "topic:future-of-work",
    )
    # Untagged, and newer than everything — so a broken focus that merely sorted
    # by date would put these first and be caught.
    put(
        "live/funders/gates-foundation/2026-09-01_e.md",
        "Grant Announcement",
        "2026-09-01T00:00:00Z",
    )
    put("live/funders/ballmer-group/2026-09-02_f.md", "Portfolio Update", "2026-09-02T00:00:00Z")
    # Tagged into a strategy it does not live in, and deliberately OLD — so a
    # focus that forgot to reorder read rows would leave it at the bottom on
    # date order and be caught.
    put(
        "live/funders/gates-foundation/2026-01-05_x.md",
        "Cross-Tagged Brief",
        "2026-01-05T00:00:00Z",
        "strategy:workforce-development",
    )
    return s


FOCUS = "strategy:workforce-development"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@pytest.mark.spec("FOCUS-01")
def test_the_tag_is_searchable_text(store: LocalFsStore) -> None:
    """The needle must exist ONLY in the tag.

    A first draft searched "literacy" and passed with the tag matching disabled,
    because the path is `live/strategies/adult-literacy-numeracy/...` and search
    already matched paths. Green, and testing nothing. `strategy:adult` cannot
    match a path — the folder is `strategies/adult`, plural and without the colon
    — so it reaches the tag or it reaches nothing.
    """
    for key in store.list(""):
        assert "strategy:adult" not in key, "the needle must not be findable in a path"

    hits = list_sources(store, search="strategy:adult")

    assert [r.title for r in hits.rows] == ["Reading Levels"]
    assert hits.rows[0].domains == ["strategy:adult-literacy-numeracy"]

    # A source tagged into a strategy it does not live in is reachable the same
    # way — this is the case a path search could never find.
    cross = list_sources(store, search="strategy:workforce")
    assert "Cross-Tagged Brief" in [r.title for r in cross.rows]

    # And the tag is carried on the row, not merely matched and discarded.
    everything = list_sources(store)
    tagged = {r.title: r.domains for r in everything.rows if r.domains}
    assert tagged["Automation Outlook"] == ["topic:future-of-work"]
    assert "Grant Announcement" not in tagged


# ---------------------------------------------------------------------------
# focus orders, it never excludes
# ---------------------------------------------------------------------------


@pytest.mark.spec("FOCUS-02")
def test_focusing_narrows_the_listing(store: LocalFsStore) -> None:
    """Only the focus's sources come back, newest first."""
    plain = list_sources(store)
    focused = list_sources(store, focus=FOCUS)

    assert plain.total == 7
    assert focused.total == 2
    assert [r.title for r in focused.rows] == ["Skills Gap Study", "Apprenticeship Report"]


@pytest.mark.spec("FOCUS-03")
def test_a_narrowed_list_says_what_it_is_a_subset_of(store: LocalFsStore) -> None:
    """ "2 in Workforce Development · 7 in the corpus" — never just "2 sources".

    A single number makes a filter look like the whole world. That is the whole
    job `corpus_total` does, and it is why narrowing here is not the same thing
    as hiding.
    """
    focused = list_sources(store, focus=FOCUS)

    assert focused.total == 2
    assert focused.corpus_total == 7

    plain = list_sources(store)
    assert plain.total == plain.corpus_total == 7


@pytest.mark.spec("FOCUS-05")
def test_the_narrowed_page_is_newest_first(store: LocalFsStore) -> None:
    """Two untagged sources are the NEWEST in the fixture, so a narrowing that
    leaked would put them first and be caught here rather than looking plausible."""
    page = list_sources(store, focus=FOCUS, limit=2)

    assert [r.title for r in page.rows] == ["Skills Gap Study", "Apprenticeship Report"]
    assert page.total == 2
    assert page.corpus_total == 7


@pytest.mark.spec("FOCUS-06")
def test_without_a_focus_nothing_changes(store: LocalFsStore) -> None:
    """Newest first, as before — the feature is additive."""
    listing = list_sources(store)

    assert [r.title for r in listing.rows][:2] == ["Portfolio Update", "Grant Announcement"]
    assert listing.total == listing.corpus_total == 7


@pytest.mark.spec("FOCUS-07")
def test_a_source_tagged_outside_its_folder_is_found_once_indexed(
    store: LocalFsStore,
) -> None:
    """**Inverted 2026-08-23.** This test used to assert the miss.

    A funder source tagged into a strategy lives in neither that folder nor its
    prefix, so key-partitioning alone cannot see it. The old spec named that gap,
    said the fix was an index rather than 845 reads, and staked this ID on it:
    *"the day it changes, a test says so."* The index shipped — see
    `context-v/specs/Search-Index.md` — so this is the day, and this is the test
    saying so.

    Both halves are still asserted, because both are still true. What changed is
    which one applies when.
    """
    # UNINDEXED, no search: still narrows on the key, so it is missed. Kept
    # because a corpus that has never been indexed has to go on working, and
    # this is exactly the reason `reindex` exists.
    plain = list_sources(store, focus=FOCUS)
    assert "Cross-Tagged Brief" not in [r.title for r in plain.rows]

    # UNINDEXED, with a search: every file is open anyway, so the tag decides.
    searched = list_sources(store, search="e", focus=FOCUS)
    titles = [r.title for r in searched.rows]
    assert "Cross-Tagged Brief" in titles
    assert "Grant Announcement" not in titles
    assert "Portfolio Update" not in titles

    # INDEXED: a plain page load consults the row for the cost of one object,
    # and finds it. The gap is closed.
    save_manifest(store, build_manifest(store))

    indexed = list_sources(store, focus=FOCUS)
    found = [r.title for r in indexed.rows]
    assert "Cross-Tagged Brief" in found
    # ...and narrowing still means narrowing: untagged funders stay out.
    assert "Grant Announcement" not in found
    assert "Portfolio Update" not in found
    assert indexed.corpus_total == 7


# ---------------------------------------------------------------------------
# the toggles
# ---------------------------------------------------------------------------


@pytest.mark.spec("FOCUS-04")
def test_the_type_vocabulary_is_read_from_the_corpus_not_assumed(tmp_path: Path) -> None:
    """No rule maps a tag to a folder, so the corpus is asked.

    `strategy`/`strategies` tempts a `+s`. **`thesis`/`theses` breaks it on the
    first try**, and this fixture is that case: a second client's corpus, using
    a type reach-edu has never heard of, nested one level deeper. Both are
    resolved from the `index.md` sitting in the folder, which states its own
    `type` and `slug`.
    """
    s = LocalFsStore(tmp_path / "corpus")

    def define(key: str, kind: str, slug: str, title: str) -> None:
        s.write(
            key,
            f'---\ntype: "{kind}"\nslug: "{slug}"\ntitle: "{title}"\n---\n\nThe case.\n'.encode(),
        )

    define("live/theses/ocean-energy/index.md", "thesis", "ocean-energy", "Ocean Energy")
    define(
        "live/verticals/health/care-delivery/index.md", "vertical", "care-delivery", "Care Delivery"
    )
    # A folder with no declaration is not a focus. Nothing is invented for it.
    s.write("live/funders/gates-foundation/2026-01-01_a.md", b'---\ntitle: "A"\n---\n\nBody.\n')

    defs = list_domain_defs(s)

    assert [d.value for d in defs] == ["thesis:ocean-energy", "vertical:care-delivery"]
    assert [d.folder for d in defs] == ["theses/ocean-energy", "verticals/health/care-delivery"]
    assert [d.title for d in defs] == ["Ocean Energy", "Care Delivery"]
    # The label an operator sees is the declared title, not the slug.
    assert [d.to_json()["label"] for d in defs] == ["Ocean Energy", "Care Delivery"]


@pytest.mark.spec("FOCUS-08")
def test_a_nested_or_unfamiliar_type_focuses_like_any_other(tmp_path: Path) -> None:
    """The whole point of reading the vocabulary: `thesis` works with no code change."""
    s = LocalFsStore(tmp_path / "corpus")
    s.write(
        "live/theses/ocean-energy/index.md",
        b'---\ntype: "thesis"\nslug: "ocean-energy"\ntitle: "Ocean Energy"\n---\n\nThe case.\n',
    )
    for key, title, when in [
        (
            "live/theses/ocean-energy/sources/2026-01-01_a.md",
            "Tidal Survey",
            "2026-01-01T00:00:00Z",
        ),
        ("live/funders/x/2026-09-01_b.md", "Unrelated Grant", "2026-09-01T00:00:00Z"),
    ]:
        s.write(key, WRAPPER.format(title=title, slug="s", fetched=when, domains="").encode())

    listing = list_sources(s, focus="thesis:ocean-energy")

    assert listing.total == 1
    assert listing.corpus_total == 2
    assert [r.title for r in listing.rows] == ["Tidal Survey"]
