"""The ledger's pure logic — parsing spec test IDs and joining them to outcomes.

Kept here, importable, rather than inside ``conftest.py`` or the CLI script, so
it can be tested directly. The harness decides whether every later spec can be
trusted; logic that can only be exercised through a live pytest run is logic
nobody actually tests.

See ``context-v/specs/Loop-Harness.md`` and
``context-v/loops/Spec-to-Shipped-With-TDD.md``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict


class TestRecord(TypedDict):
    """One test function's contribution to a spec ID."""

    nodeid: str
    outcome: str


class SpecEntry(TypedDict):
    """The joined state of one spec ID: worst outcome plus its claimants."""

    outcome: str
    tests: list[TestRecord]


GREEN = "GREEN"
RED = "RED"
MISSING = "MISSING"
RETIRED = "RETIRED"
#: A test that exists and deliberately did not run — its gate (an env var, a
#: sibling repo, real credentials) was not set. Not a failure: skipping is what
#: the gate is FOR. But not green either, so --require-green still refuses to
#: call a spec complete until someone has actually run it.
GATED = "GATED"

#: Worst-wins ordering. A test that errors during setup is not green merely
#: because its never-executed call phase did not fail.
SEVERITY = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}

#: CAPTURE-01, STORE-R2-14, HISTORY-03 — an uppercase stem plus a numeric tail.
ID_PATTERN = re.compile(r"`(~~)?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{2,})(~~)?`")
_TESTS_HEADING = re.compile(r"^##+\s+Tests\b", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^##+\s+")


def parse_spec_ids(path: Path) -> tuple[list[str], list[str]]:
    """Return ``(active_ids, retired_ids)`` from a spec's ``## Tests`` section.

    IDs mentioned outside that section are ignored, so prose may reference an ID
    without enrolling it as a promise. A struck-through ID (``~~ID~~``) is
    retired: excluded from totals, never renumbered, never reused.
    """
    active: list[str] = []
    retired: list[str] = []
    in_tests = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if _TESTS_HEADING.match(line):
            in_tests = True
            continue
        if in_tests and _ANY_HEADING.match(line):
            break  # the next heading ends the section
        if not in_tests:
            continue
        for open_strike, spec_id, close_strike in ID_PATTERN.findall(line):
            target = retired if (open_strike and close_strike) else active
            if spec_id not in target:
                target.append(spec_id)

    return active, retired


def worst(outcomes: list[str]) -> str:
    """Return the most severe outcome in ``outcomes``."""
    if not outcomes:
        return "error"
    return max(outcomes, key=lambda o: SEVERITY.get(o, SEVERITY["error"]))


def join_outcomes(
    spec_ids_by_node: dict[str, list[str]],
    outcome_by_node: dict[str, str],
) -> dict[str, SpecEntry]:
    """Join collected spec markers to test outcomes.

    ``spec_ids_by_node`` maps a pytest nodeid to the spec IDs it claims;
    ``outcome_by_node`` maps a nodeid to its worst observed outcome. A spec ID
    claimed by several tests resolves to the **worst** of them — one failing
    claimant makes the ID red however many others pass, because the spec
    promised all of it.
    """
    per_spec: dict[str, SpecEntry] = {}

    for nodeid, ids in spec_ids_by_node.items():
        outcome = outcome_by_node.get(nodeid, "error")
        for spec_id in ids:
            entry = per_spec.setdefault(spec_id, {"outcome": outcome, "tests": []})
            entry["tests"].append({"nodeid": nodeid, "outcome": outcome})
            entry["outcome"] = worst([entry["outcome"], outcome])

    for entry in per_spec.values():
        entry["tests"].sort(key=lambda t: t["nodeid"])

    return per_spec


def classify(spec_id: str, results: dict[str, SpecEntry]) -> str:
    """Return GREEN, RED, or MISSING for one spec ID against a results map."""
    entry = results.get(spec_id)
    if entry is None:
        return MISSING
    outcome = entry.get("outcome")
    if outcome == "passed":
        return GREEN
    if outcome == "skipped":
        return GATED
    return RED
