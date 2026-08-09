"""Tests for the source-file model — spec: context-v/specs/Source-File-Model.md.

Two of these encode bugs this tree already paid for, and they are the reason the
phase exists rather than nice-to-haves:

  PARSE-01   the stray `---` that hid 13 of ImmuneCo's 93 sources for three
             weeks, visible to grep and invisible to every consumer
  SOURCE-10  the round-trip that stripped `sensitivity` from eight sources,
             silently downgrading the flag that governs external citability

Everything writes under tmp_path. No client corpus is touched.
"""

from __future__ import annotations

import pytest

from src.model import (
    FIELD_ORDER,
    BinaryAsset,
    SourceFile,
    StrandedContent,
    normalize_url,
    parse_frontmatter,
    slugify,
    source_filename,
)


def _full_source() -> SourceFile:
    return SourceFile(
        url="https://www.ocean-energy-systems.org/news/iea-oes-annual-report/",
        normalized_url="ocean-energy-systems.org/news/iea-oes-annual-report",
        title="IEA-OES Annual Report",
        publisher="IEA Ocean Energy Systems",
        authors=["A. Analyst"],
        fetched_at="2026-06-27T14:31:00Z",
        published_at="2025-03-01",
        status="promoted",
        content_pulled=True,
        excerpt="The IEA-OES annual report finds installed capacity reached…",
        description="Annual stocktake of global ocean-energy capacity.",
        origin="searxng",
        origin_detail={"search_query": "ocean energy market size", "engine": "google"},
        domains=["ocean-energy"],
        sections=["opportunity"],
        tags=["Marine-Energy"],
        rank=1,
        sensitivity="citable_externally",
        verdict="approved",
        verdict_reason="primary source, current",
        machine_verdict="HTTP 200 (body verified)",
        confidence="high",
        note="",
        binary_asset=BinaryAsset(
            filename="iea-oes-annual-report-2025.pdf",
            bytes=4210332,
            sha256="abc123",
            downloaded_at="2026-06-27T14:32:10Z",
            download_status="ok",
        ),
        body="# Extracts\n\n## Quotes\n\n> Capacity reached 1.2 GW.\n",
    )


# ---------------------------------------------------------------------------
# Round-trip and the schema's three rulings
# ---------------------------------------------------------------------------


@pytest.mark.spec("SOURCE-01")
def test_a_fully_populated_source_round_trips() -> None:
    original = _full_source()

    assert SourceFile.parse(original.render()) == original


@pytest.mark.spec("SOURCE-02")
def test_unknown_frontmatter_keys_survive() -> None:
    """An older reader must never delete a newer writer's fields."""
    text = "---\nurl: https://example.org/a\nsome_future_field: kept\n---\n\nbody\n"

    reparsed = SourceFile.parse(SourceFile.parse(text).render())

    assert reparsed.unknown["some_future_field"] == "kept"
    assert "some_future_field: kept" in reparsed.render()


@pytest.mark.spec("SOURCE-03")
def test_fetched_at_and_published_at_stay_distinct() -> None:
    source = SourceFile(
        url="https://example.org/a",
        fetched_at="2026-06-27T14:31:00Z",
        published_at="2025-03-01",
    )

    parsed = SourceFile.parse(source.render())

    assert parsed.fetched_at == "2026-06-27T14:31:00Z"
    assert parsed.published_at == "2025-03-01"


@pytest.mark.spec("SOURCE-04")
def test_status_and_content_pulled_are_independent() -> None:
    """Promoted with nothing fetched yet is a real, expressible state."""
    source = SourceFile(url="https://example.org/a", status="promoted", content_pulled=False)

    parsed = SourceFile.parse(source.render())

    assert parsed.status == "promoted"
    assert parsed.content_pulled is False


@pytest.mark.spec("SOURCE-05")
def test_frontmatter_keys_follow_field_order() -> None:
    """Fixed order so a diff shows what changed, not a reshuffle."""
    rendered = _full_source().render()

    emitted = [
        line.split(":", 1)[0]
        for line in rendered.splitlines()[1:]
        if line and not line.startswith((" ", "-", "#")) and ":" in line and line != "---"
    ]
    known = [k for k in emitted if k in FIELD_ORDER]

    assert known == sorted(known, key=FIELD_ORDER.index)
    assert known[0] == "url"


@pytest.mark.spec("SOURCE-06")
def test_machine_verdict_never_becomes_an_analyst_verdict() -> None:
    """Reachability is not approval. 34 sources once said otherwise."""
    source = SourceFile(
        url="https://example.org/a",
        machine_verdict="HTTP 200 (body verified)",
        verdict="",
    )

    parsed = SourceFile.parse(source.render())

    assert parsed.machine_verdict == "HTTP 200 (body verified)"
    assert parsed.verdict == ""


@pytest.mark.spec("SOURCE-07")
def test_extracts_body_survives_a_rewrite_byte_identical() -> None:
    body = "# Extracts\n\n## Quotes\n\n> A quote with: colons, $dollars, and [brackets].\n"
    source = SourceFile(url="https://example.org/a", body=body)

    assert SourceFile.parse(source.render()).body == body


@pytest.mark.spec("SOURCE-08")
def test_a_failed_download_is_recorded_not_omitted() -> None:
    source = SourceFile(
        url="https://example.org/a",
        binary_asset=BinaryAsset(filename="report.pdf", download_status="http_error"),
    )

    parsed = SourceFile.parse(source.render())

    assert parsed.binary_asset is not None
    assert parsed.binary_asset.download_status == "http_error"


@pytest.mark.spec("SOURCE-09")
def test_url_only_frontmatter_is_valid() -> None:
    parsed = SourceFile.parse("---\nurl: https://example.org/a\n---\n")

    assert parsed.url == "https://example.org/a"
    assert parsed.title == ""
    assert "title:" not in parsed.render()


@pytest.mark.spec("SOURCE-10")
def test_sensitivity_survives_a_caller_that_never_mentions_it() -> None:
    """The exact 2026-08-08 failure: eight sources silently downgraded."""
    on_disk = "---\nurl: https://example.org/a\nsensitivity: internal_only\n---\n\nbody\n"

    loaded = SourceFile.parse(on_disk)
    loaded.note = "an unrelated edit"

    assert SourceFile.parse(loaded.render()).sensitivity == "internal_only"


# ---------------------------------------------------------------------------
# The parser bugs
# ---------------------------------------------------------------------------


@pytest.mark.spec("PARSE-01")
def test_stranded_frontmatter_raises_rather_than_hiding() -> None:
    """ImmuneCo, 2026-07-14: 13 of 93 sources invisible for three weeks."""
    text = (
        "---\n"
        "url: https://example.org/a\n"
        "---\n"
        "title: Stranded Report\n"
        "publisher: Someone\n"
        "fetched_at: 2026-07-14\n"
    )

    with pytest.raises(StrandedContent) as excinfo:
        SourceFile.parse(text)

    assert "title" in str(excinfo.value)


@pytest.mark.spec("PARSE-02")
def test_a_horizontal_rule_in_the_body_is_not_stranded_content() -> None:
    """Prose legitimately contains `---`. Only orphaned key: value lines count."""
    text = "---\nurl: https://example.org/a\n---\n\nSome prose.\n\n---\n\nMore prose.\n"

    parsed = SourceFile.parse(text)

    assert "More prose." in parsed.body


@pytest.mark.spec("PARSE-03")
def test_a_file_with_no_frontmatter_parses_as_all_body() -> None:
    data, body = parse_frontmatter("Just some markdown.\n")

    assert data == {}
    assert body == "Just some markdown.\n"


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("IEA-OES Annual Report", "iea-oes-annual-report"),
        ("State of Digital Health Q1'26", "state-of-digital-health-q1-26"),
        ("  Trailing & leading  ", "trailing-leading"),
        ("Über Café — München", "uber-cafe-munchen"),
    ],
)
@pytest.mark.spec("NAME-01")
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


@pytest.mark.spec("NAME-01")
def test_filename_is_date_underscore_slug() -> None:
    assert (
        source_filename("IEA-OES Annual Report", "2026-06-27")
        == "2026-06-27_iea-oes-annual-report.md"
    )


@pytest.mark.spec("NAME-02")
def test_untitled_falls_back_to_the_url_not_to_untitled() -> None:
    name = source_filename("", "2026-06-27", url="https://example.org/a/b")

    assert name == "2026-06-27_example-org-a-b.md"
    assert "untitled" not in name


@pytest.mark.spec("NAME-03")
def test_collisions_gain_a_numeric_suffix_and_binaries_share_the_stem() -> None:
    taken = ["2026-06-27_report.md"]

    assert source_filename("Report", "2026-06-27", taken=taken) == "2026-06-27_report_2.md"
    assert source_filename("Report", "2026-06-27", suffix=".pdf") == "2026-06-27_report.pdf"


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------


@pytest.mark.spec("URL-01")
def test_cosmetic_url_differences_collapse_to_one_key() -> None:
    variants = [
        "https://www.example.org/a/b/",
        "http://example.org/a/b",
        "https://example.org:443/a/b",
        "https://example.org/a/b#section",
        "https://example.org/a/b?utm_source=twitter&fbclid=xyz",
    ]

    keys = {normalize_url(u) for u in variants}

    assert len(keys) == 1, f"expected one key, got {keys}"


@pytest.mark.spec("URL-02")
def test_meaningful_query_parameters_are_not_collapsed() -> None:
    """Over-collapsing loses evidence — two articles becoming one source."""
    a = normalize_url("https://example.org/search?q=ocean")
    b = normalize_url("https://example.org/search?q=solar")

    assert a != b


# ---------------------------------------------------------------------------
# Generation-A aliases — read them, never rewrite them
# ---------------------------------------------------------------------------


@pytest.mark.spec("SOURCE-11")
def test_generation_a_aliases_populate_the_canonical_fields() -> None:
    """637 of 845 real files use `exact_url`. A reader blind to it is blind."""
    text = (
        "---\n" "exact_url: https://example.org/a\n" "published_date: 2025-03-01\n" "---\n\nbody\n"
    )

    parsed = SourceFile.parse(text)

    assert parsed.url == "https://example.org/a"
    assert parsed.published_at == "2025-03-01"


@pytest.mark.spec("SOURCE-12")
def test_aliases_are_re_emitted_under_their_original_key() -> None:
    """Reading a file is not consent to migrate its schema."""
    text = "---\nexact_url: https://example.org/a\n---\n\nbody\n"

    rendered = SourceFile.parse(text).render()

    assert "exact_url: https://example.org/a" in rendered
    assert "\nurl:" not in rendered


@pytest.mark.spec("PARSE-04")
def test_plain_markdown_does_not_acquire_frontmatter_on_rewrite() -> None:
    """A corpus directory holds READMEs and notes too. Do not graft onto them."""
    text = "# A README\n\nJust prose, no frontmatter.\n"

    assert SourceFile.parse(text).render() == text


@pytest.mark.spec("SOURCE-13")
def test_parsing_then_rendering_does_not_accrete_defaults() -> None:
    """`status: candidate` on a file that said `inbox_status: discarded` is an
    assertion the file never made."""
    text = "---\nexact_url: https://example.org/a\ninbox_status: discarded\n---\n\nbody\n"

    rendered = SourceFile.parse(text).render()

    assert "status: candidate" not in rendered
    assert "content_pulled:" not in rendered
    assert "rank:" not in rendered
    assert "inbox_status: discarded" in rendered
