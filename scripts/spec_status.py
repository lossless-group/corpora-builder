#!/usr/bin/env python3
"""The ledger — derive spec status by running the suite, never by reading prose.

Every spec in ``context-v/specs/`` carries a ``## Tests`` table whose rows each
begin with a stable ID. Every test function that implements one carries
``@pytest.mark.spec("<ID>")``. This script joins the two and reports the truth.

    GREEN     a test claims the ID and passes
    RED       a test claims the ID and does not pass
    MISSING   the spec promises a behaviour that no test function claims
    RETIRED   the ID is struck through in the spec (~~ID~~); excluded from totals

Usage
-----
    uv run python scripts/spec_status.py                 # from the repo root
    uv run python scripts/spec_status.py --spec Loop-Harness
    uv run python scripts/spec_status.py --require-green # spec-completion gate
    uv run python scripts/spec_status.py --tdd-floor     # after writing failing tests
    uv run python scripts/spec_status.py --no-run        # reuse last results

Exit codes
----------
    0  the requested condition holds
    1  MISSING IDs exist (always fatal — a promise with no test)
    2  --require-green was asked for and something is not green
    3  --tdd-floor was asked for and something is already green

Why MISSING is always fatal: it is the one failure mode that looks like success.
A spec table that grew a row nobody implemented reports "all tests pass" forever.
A non-zero exit turns "I forgot" into a build failure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "context-v" / "specs"
RESULTS_PATH = REPO_ROOT / ".spec-results.json"
APP_RESULTS_PATH = REPO_ROOT / "app" / ".spec-results.json"

sys.path.insert(0, str(REPO_ROOT))

from src.ledger import (  # noqa: E402
    GATED,
    GREEN,
    MISSING,
    RED,
    RETIRED,
    classify,
    parse_spec_ids,
)

_GLYPH = {GREEN: "✓", RED: "✗", MISSING: "○", RETIRED: "—", GATED: "⊘"}
_BOLD, _DIM, _OFF = "\033[1m", "\033[2m", "\033[0m"
_REDC, _GREENC = "\033[31m", "\033[32m"


def run_frontend_tests() -> int:
    """Run the app's tests so `app/.spec-results.json` is fresh.

    Frontend promises are promises. Before this existed the ledger only saw
    pytest, so a spec covered by `node --test` would have reported MISSING —
    and the tempting fix for MISSING is deleting the row, which turns a real
    promise into no promise at all.

    Absent node, this reports and returns 0 rather than failing: the Python side
    has to stay runnable on a machine that has never built the frontend.
    """
    app = REPO_ROOT / "app"
    if not (app / "scripts" / "run-tests.mjs").exists():
        return 0
    if shutil.which("node") is None:
        print("  frontend: skipped — node not on PATH")
        return 0
    return subprocess.run(
        [shutil.which("node") or "node", "scripts/run-tests.mjs"], cwd=app
    ).returncode


def run_pytest() -> int:
    """Run the suite so the results file is fresh. Returns pytest's exit code."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line"],
        cwd=REPO_ROOT,
    )
    return proc.returncode


def load_results(path: Path = RESULTS_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--spec", help="only this spec (filename stem, substring ok)")
    parser.add_argument("--no-run", action="store_true", help="reuse the last results")
    parser.add_argument(
        "--require-green",
        action="store_true",
        help="exit non-zero unless every active ID is GREEN (spec-completion gate)",
    )
    parser.add_argument(
        "--tdd-floor",
        action="store_true",
        help="exit non-zero unless every active ID exists and is RED (TDD step 4)",
    )
    args = parser.parse_args()

    if not SPECS_DIR.exists():
        print(f"No specs directory at {SPECS_DIR}", file=sys.stderr)
        return 0

    spec_files = sorted(p for p in SPECS_DIR.glob("*.md") if not p.name.startswith("_"))
    if args.spec:
        needle = args.spec.lower()
        spec_files = [p for p in spec_files if needle in p.stem.lower()]
        if not spec_files:
            print(f"No spec matching {args.spec!r}", file=sys.stderr)
            return 1

    if not args.no_run:
        run_pytest()
        run_frontend_tests()
        print()
    results = load_results()
    # Frontend IDs merge into the same map. The two suites cover disjoint specs,
    # so a plain update is right; were that ever to stop being true, the collision
    # should be loud rather than silently resolved by ordering.
    for spec_id, entry in load_results(APP_RESULTS_PATH).items():
        if spec_id in results:
            print(f"  [!] {spec_id} is claimed by BOTH suites — frontend result ignored")
            continue
        results[spec_id] = entry

    totals = {GREEN: 0, RED: 0, MISSING: 0, RETIRED: 0, GATED: 0}
    saw_any = False

    for spec_file in spec_files:
        active, retired = parse_spec_ids(spec_file)
        if not active and not retired:
            continue
        saw_any = True

        rows = [(sid, classify(sid, results)) for sid in active]
        rows += [(sid, RETIRED) for sid in retired]
        for _, status in rows:
            totals[status] += 1

        green = sum(1 for _, s in rows if s == GREEN)
        print(f"{_BOLD}{spec_file.stem}{_OFF}  ({green}/{len(active)} green)")
        for spec_id, status in rows:
            colour = _GREENC if status == GREEN else (_REDC if status in (RED, MISSING) else _DIM)
            print(f"  {colour}{_GLYPH[status]} {status:<8}{_OFF} {spec_id}")
        print()

    if not saw_any:
        print("No spec carries a `## Tests` table yet — nothing to derive.")
        return 0

    print(
        f"{_BOLD}Totals{_OFF}  {totals[GREEN]} green · {totals[RED]} red · "
        f"{totals[GATED]} gated · {totals[MISSING]} missing · {totals[RETIRED]} retired"
    )

    if totals[MISSING]:
        print(
            f"\n{_REDC}FAIL{_OFF}  {totals[MISSING]} spec test ID(s) have no "
            f"implementing test.\n"
            f"      A promise with no test is the one failure that looks like success.\n"
            f'      Add @pytest.mark.spec("<ID>") to the test that proves each.',
            file=sys.stderr,
        )
        return 1

    if args.require_green and (totals[RED] or totals[GATED]):
        print(
            f"\n{_REDC}FAIL{_OFF}  --require-green: {totals[RED]} red, "
            f"{totals[GATED]} gated. The spec is not complete.\n"
            f"      A gated ID means a deliberate run nobody has done yet — set "
            f"its env var and run it.\n"
            f"      Do NOT edit a test to close this gap — see "
            f"context-v/contracts/Autonomy-Gates.md, Gate 3.",
            file=sys.stderr,
        )
        return 2

    structural_green = sum(
        1
        for f in spec_files
        for sid in parse_spec_ids(f)[0]
        if classify(sid, results) == GREEN and results.get(sid, {}).get("structural")
    )
    if args.tdd_floor and (totals[GREEN] - structural_green):
        print(
            f"\n{_REDC}FAIL{_OFF}  --tdd-floor: "
            f"{totals[GREEN] - structural_green} ID(s) are already green "
            f"before implementation.\n"
            f"      A test that passes before the code exists is not testing the code.",
            file=sys.stderr,
        )
        return 3

    if totals[RED]:
        # Red is the expected state mid-TDD, so this is not a failure — but it is
        # emphatically not "OK" either. Never round a red suite up to a success.
        print(f"\n{_REDC}{totals[RED]} red{_OFF} — expected during TDD, not at completion.")
        return 0

    print(f"\n{_GREENC}OK{_OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
