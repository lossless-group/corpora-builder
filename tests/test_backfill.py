"""Covers the backfill rows of `context-v/specs/Source-File-Model.md`.

The operation is deliberately boring, and the tests are about it *staying*
boring: it runs against a corpus that belongs to a client, so the interesting
assertion is not what it changes but what it leaves alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.model.backfill import apply as apply_backfill
from src.model.backfill import apply_one, plan, plan_one
from src.store import LocalFsStore

WITH_URL = """---
title: "A Report"
url: "https://Example.org/a/?utm_source=newsletter&id=7"
publisher: "Someone"
status: "fetched"
domains:
  - "strategy:workforce-development"
tags:
  - "Workforce-Development"
---

Body prose that should survive untouched, including a stray url: line.
"""


@pytest.mark.spec("BACKFILL-01")
def test_the_normalised_form_is_derived_with_no_network() -> None:
    """Every one of reach-edu's 737 filed sources carries a `url:`, so identity
    is available for nothing — 511 of them lack only this."""
    entry = plan_one("live/funders/x/a.md", WITH_URL)

    assert entry.writes
    assert entry.url == "https://Example.org/a/?utm_source=newsletter&id=7"
    # Lower-cased host, tracking dropped, meaningful params kept.
    assert entry.normalized == "example.org/a?id=7"


@pytest.mark.spec("BACKFILL-02")
@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (
            WITH_URL.replace('url: "https', 'normalized_url: "example.org/a"\nurl: "https'),
            "already has one",
        ),
        ('---\ntitle: "No URL"\n---\n\nBody.\n', "no url"),
        ("Just a body with no frontmatter at all.\n", "no frontmatter"),
        ('---\ntitle: "Unclosed"\nurl: "https://example.org/x"\n', "no frontmatter"),
    ],
)
def test_a_file_that_needs_nothing_is_skipped_with_a_reason(text: str, reason: str) -> None:
    """A stated reason, not a silent pass. The unclosed-fence case matters most:
    that is a damaged file, and a backfill should not be the first thing to write
    to one."""
    entry = plan_one("k.md", text)

    assert not entry.writes
    assert entry.skipped == reason


@pytest.mark.spec("BACKFILL-03")
def test_exactly_one_line_changes_and_nothing_else_does() -> None:
    """The whole value of this operation is that a client can read the diff.

    A `parse` → `render` round-trip would reorder keys through `FIELD_ORDER` and
    reflow values nothing asked to change, across 511 files at once.
    """
    entry = plan_one("k.md", WITH_URL)
    after = apply_one(WITH_URL, entry)

    before_lines = WITH_URL.splitlines()
    after_lines = after.splitlines()
    assert len(after_lines) == len(before_lines) + 1

    added = [ln for ln in after_lines if ln not in before_lines]
    assert added == ['normalized_url: "example.org/a?id=7"']

    # ...and it sits directly beneath `url:`, where FIELD_ORDER puts it, so a
    # later re-render is a no-op rather than a move.
    url_line = 'url: "https://Example.org/a/?utm_source=newsletter&id=7"'
    assert after_lines[after_lines.index(url_line) + 1] == added[0]

    # Every other line, in order, byte for byte.
    assert [ln for ln in after_lines if ln != added[0]] == before_lines
    # The body — including the decoy `url:` inside it — is untouched.
    assert after.endswith(
        "Body prose that should survive untouched, including a stray url: line.\n"
    )


@pytest.mark.spec("BACKFILL-04")
def test_a_second_pass_writes_nothing(tmp_path: Path) -> None:
    class Counting(LocalFsStore):
        def __init__(self, root) -> None:  # type: ignore[no-untyped-def]
            super().__init__(root)
            self.writes = 0

        def write(self, key: str, data: bytes) -> None:
            self.writes += 1
            super().write(key, data)

    s = Counting(tmp_path / "c")
    for i in range(3):
        s.write(f"live/funders/x/2026-01-0{i}_a.md", WITH_URL.encode())
    s.writes = 0

    keys = sorted(s.list(""))
    first = apply_backfill(s, plan(s, keys))
    after_first = s.writes
    second = apply_backfill(s, plan(s, keys))

    assert first == 3
    assert after_first == 3
    assert second == 0, "re-running must be a no-op"
    assert s.writes == 3


@pytest.mark.spec("BACKFILL-05")
def test_a_dry_run_changes_nothing(tmp_path: Path) -> None:
    """Planning reads. Only `apply` writes — asserted on the bytes, because
    'the dry run is safe' is exactly the claim nobody wants to take on trust."""
    s = LocalFsStore(tmp_path / "c")
    s.write("live/funders/x/2026-01-01_a.md", WITH_URL.encode())
    before = {k: s.read(k) for k in s.list("")}

    result = plan(s, sorted(s.list("")))

    assert len(result.writes) == 1
    assert {k: s.read(k) for k in s.list("")} == before


ALIASED = """---
title: "Generation A"
exact_url: "https://Example.org/legacy/?utm_campaign=z"
fulltext_url: "https://example.org/legacy/full"
status: "candidate"
---

Body.
"""


@pytest.mark.spec("BACKFILL-06")
def test_the_generation_a_key_counts_as_a_url() -> None:
    """**Found by running it, not by a fixture.** A dry run against reach-edu
    reported "590 no url" for a corpus where every source has one: 589 of 832
    carry the Generation-A key `exact_url:`, and a literal `^url:` sees none of
    them. The key list is derived from `FIELD_ALIASES` so it cannot drift.
    """
    from src.model.backfill import URL_KEYS

    assert "exact_url" in URL_KEYS

    entry = plan_one("k.md", ALIASED)

    assert entry.writes
    assert entry.normalized == "example.org/legacy"

    after = apply_one(ALIASED, entry)
    lines = after.splitlines()
    # Inserted under the key the file actually uses...
    at = lines.index('exact_url: "https://Example.org/legacy/?utm_campaign=z"')
    assert lines[at + 1] == 'normalized_url: "example.org/legacy"'
    # ...and the original key is NOT migrated — SOURCE-12, reading a corpus
    # never silently changes its schema.
    assert "\nurl:" not in after
    assert 'exact_url: "https://Example.org/legacy/?utm_campaign=z"' in after
    # A neighbouring key that merely ends in `url` is not the URL.
    assert 'fulltext_url: "https://example.org/legacy/full"' in after


@pytest.mark.spec("BACKFILL-06")
def test_the_canonical_key_wins_when_a_file_carries_both() -> None:
    """47 files in reach-edu carry `exact_url`, `url` and `normalized_url` at
    once. A file mid-migration follows the parser's rule: canonical wins."""
    both = ALIASED.replace(
        'exact_url: "https://Example.org/legacy/?utm_campaign=z"',
        'exact_url: "https://example.org/old"\nurl: "https://example.org/new"',
    )

    entry = plan_one("k.md", both)

    assert entry.url == "https://example.org/new"
    lines = apply_one(both, entry).splitlines()
    assert lines[lines.index('url: "https://example.org/new"') + 1] == (
        'normalized_url: "example.org/new"'
    )
