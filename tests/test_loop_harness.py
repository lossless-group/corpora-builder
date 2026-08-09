"""Tests for the loop harness itself — spec: context-v/specs/Loop-Harness.md.

The harness decides whether every later spec can be trusted, so its logic is
exercised directly through :mod:`corpora.ledger` rather than by inspecting the
artifacts of a previous run. A test that reads last run's output can only ever
tell you about last run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ledger import GREEN, MISSING, RED, classify, join_outcomes, parse_spec_ids


@pytest.mark.spec("HARNESS-01")
def test_marked_test_binds_to_its_id_with_its_outcome() -> None:
    spec_ids = {"tests/test_capture.py::test_writes_file": ["CAPTURE-01"]}
    outcomes = {"tests/test_capture.py::test_writes_file": "passed"}

    results = join_outcomes(spec_ids, outcomes)

    assert results["CAPTURE-01"]["outcome"] == "passed"
    assert results["CAPTURE-01"]["tests"] == [
        {"nodeid": "tests/test_capture.py::test_writes_file", "outcome": "passed"}
    ]


@pytest.mark.spec("HARNESS-02")
def test_active_ids_are_parsed_from_the_tests_table(tmp_path: Path) -> None:
    spec_file = tmp_path / "Sample.md"
    spec_file.write_text(
        "# Sample\n\n"
        "Prose mentioning `NOISE-99` outside the section must be ignored.\n\n"
        "## Tests\n\n"
        "| ID | Given / When / Then |\n"
        "|---|---|\n"
        "| `CAPTURE-01` | something observable |\n"
        "| `STORE-R2-14` | something else observable |\n"
    )

    active, retired = parse_spec_ids(spec_file)

    assert active == ["CAPTURE-01", "STORE-R2-14"]
    assert retired == []
    assert "NOISE-99" not in active


@pytest.mark.spec("HARNESS-03")
def test_struck_ids_are_retired_not_active(tmp_path: Path) -> None:
    spec_file = tmp_path / "Sample.md"
    spec_file.write_text(
        "## Tests\n\n"
        "| ID | Given / When / Then |\n"
        "|---|---|\n"
        "| `CAPTURE-01` | still promised |\n"
        "| `~~CAPTURE-02~~` | withdrawn — dedup moved to STORE-07 |\n"
    )

    active, retired = parse_spec_ids(spec_file)

    assert active == ["CAPTURE-01"]
    assert retired == ["CAPTURE-02"]


@pytest.mark.spec("HARNESS-04")
def test_unclaimed_id_is_missing() -> None:
    results = {"CAPTURE-01": {"outcome": "passed", "tests": []}}

    assert classify("CAPTURE-01", results) == GREEN
    assert classify("CAPTURE-99", results) == MISSING


@pytest.mark.spec("HARNESS-05")
def test_worst_outcome_wins_across_tests_claiming_one_id() -> None:
    """One failing claimant makes the ID red, however many others pass."""
    spec_ids = {
        "tests/a.py::passes": ["CAPTURE-01"],
        "tests/b.py::fails": ["CAPTURE-01"],
    }
    outcomes = {"tests/a.py::passes": "passed", "tests/b.py::fails": "failed"}

    results = join_outcomes(spec_ids, outcomes)

    assert results["CAPTURE-01"]["outcome"] == "failed"
    assert classify("CAPTURE-01", results) == RED


@pytest.mark.spec("HARNESS-06")
def test_tests_section_ends_at_the_next_heading(tmp_path: Path) -> None:
    spec_file = tmp_path / "Sample.md"
    spec_file.write_text(
        "## Tests\n\n"
        "| `CAPTURE-01` | in scope |\n\n"
        "## Acceptance\n\n"
        "Mentioning `LATER-42` here must not enrol it as a promised test.\n"
    )

    active, _ = parse_spec_ids(spec_file)

    assert active == ["CAPTURE-01"]
    assert "LATER-42" not in active
