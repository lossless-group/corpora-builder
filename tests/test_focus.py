"""Covers `context-v/specs/Strategy-Focus.md`.

The single property under protection: **focus orders, it never excludes.** Every
test that touches a listing asserts the total is unchanged, because the whole
reason the `domains:` tag exists is to keep the rest of the client's corpus
reachable while you draft against part of it. A focus that quietly filtered would
pass a naive "the right rows came back" check and destroy the feature.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.server.browse import list_domain_defs, list_sources
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
def test_focusing_reorders_and_returns_everything(store: LocalFsStore) -> None:
    """The property the whole feature rests on.

    A filter would return 2 rows and look correct to anyone checking that the
    right sources came back. It would also remove exactly the access the tag
    exists to preserve — all of the client's corpus, with a pointer.
    """
    plain = list_sources(store)
    focused = list_sources(store, focus=FOCUS)

    assert focused.total == plain.total == 7  # nothing hidden
    assert [r.title for r in focused.rows][:2] == ["Skills Gap Study", "Apprenticeship Report"]
    assert {r.title for r in focused.rows} == {r.title for r in plain.rows}


@pytest.mark.spec("FOCUS-03")
def test_both_numbers_are_reported(store: LocalFsStore) -> None:
    """ "34 to start with, 845 available" — never "34 sources"."""
    focused = list_sources(store, focus=FOCUS)

    assert focused.total == 7
    # Two, not three. `Cross-Tagged Brief` carries the tag but lives under
    # `funders/`, and this count is partitioned on the key so that ordering the
    # whole corpus costs no reads. That gap is the one `Strategy-Focus.md`
    # names, and it is asserted here rather than glossed: a number that silently
    # drifts from the truth is worse than one whose limit is written down.
    assert focused.focused_total == 2

    assert list_sources(store).focused_total == 0


@pytest.mark.spec("FOCUS-05")
def test_a_short_page_holds_only_focused_sources(store: LocalFsStore) -> None:
    """The date sort must not undo the focus ordering.

    Two of the untagged sources are the NEWEST in the fixture precisely so that a
    focus that forgot to suppress the fetched_at sort would fail here.
    """
    page = list_sources(store, focus=FOCUS, limit=2)

    assert [r.title for r in page.rows] == ["Skills Gap Study", "Apprenticeship Report"]
    assert page.total == 7


@pytest.mark.spec("FOCUS-06")
def test_without_a_focus_nothing_changes(store: LocalFsStore) -> None:
    """Newest first, as before — the feature is additive."""
    rows = list_sources(store).rows

    assert [r.title for r in rows][:2] == ["Portfolio Update", "Grant Announcement"]
    assert list_sources(store).focused_total == 0


@pytest.mark.spec("FOCUS-07")
def test_a_source_tagged_outside_its_folder_still_sorts_as_focused(
    store: LocalFsStore,
) -> None:
    """The case key-partitioning alone cannot see.

    A funder source tagged into a strategy lives in neither that folder nor its
    prefix. Once the row is read its real `domains:` decides, which is why the
    sort consults the tag as well as the path — and why the spec says plainly
    that discovering such a source across the whole corpus needs an index.
    """
    hits = list_sources(store, search="Brief", focus=FOCUS)
    assert [r.title for r in hits.rows] == ["Cross-Tagged Brief"]
    assert hits.rows[0].domains == [FOCUS]

    # The load-bearing assertion. Cross-Tagged Brief is the OLDEST source in the
    # fixture; Grant Announcement and Portfolio Update are the newest. On date
    # order alone it sorts last, so it can only lead here if the tag decided.
    everything = list_sources(store, search="e", focus=FOCUS)
    titles = [r.title for r in everything.rows]
    assert "Grant Announcement" in titles and "Portfolio Update" in titles
    assert titles.index("Cross-Tagged Brief") < titles.index("Grant Announcement")
    assert titles.index("Cross-Tagged Brief") < titles.index("Portfolio Update")


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

    assert listing.total == 2  # nothing hidden
    assert listing.focused_total == 1
    assert [r.title for r in listing.rows][0] == "Tidal Survey"
