#!/usr/bin/env bash
#
# The full check ladder, cheapest rung first — see
# context-v/loops/Spec-to-Shipped-With-TDD.md §⑤.
#
# Blocking:     black --check · ruff check · pytest · frontend tests · design drift
# Non-blocking: mypy
#
# mypy reports but never gates. memopop-orchestrator runs no type checker at
# all; corpora-builder keeps one for the storage and schema layers, where
# silent type drift is expensive. The risk of a non-blocking check is that it
# decays into noise nobody reads — so its count is printed here, in the output
# every run produces, rather than hidden behind a command someone has to
# remember. If that count climbs and stays climbed, promote it to blocking.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

FAILED=0
hdr() { printf '\n\033[1m── %s\033[0m\n' "$1"; }

hdr "black --check"
uv run black --check . || FAILED=1

hdr "ruff check"
uv run ruff check . || FAILED=1

hdr "design drift"
# The token rules stated in app/src/lib/styles/tokens.css, as checks. Skipped
# rather than failed when node is absent — the Python side must stay runnable
# on a machine that has never built the frontend.
if command -v node >/dev/null 2>&1; then
  node app/scripts/design-drift.mjs || FAILED=1
else
  echo "  skipped — node not on PATH"
fi

hdr "mypy (non-blocking)"
MYPY_OUT="$(uv run mypy 2>&1)"
echo "$MYPY_OUT"
MYPY_ERRS="$(printf '%s' "$MYPY_OUT" | grep -cE '^[^ ].*: error:' || true)"

hdr "pytest"
uv run pytest -q || FAILED=1

hdr "frontend tests"
# Writes app/.spec-results.json, which the ledger below merges — frontend
# promises are promises. Skipped rather than failed when node is absent.
if command -v node >/dev/null 2>&1; then
  (cd app && node scripts/run-tests.mjs) || FAILED=1
else
  echo "  skipped — node not on PATH"
fi

hdr "ledger"
uv run python scripts/spec_status.py --no-run || FAILED=1

printf '\n\033[1m── summary\033[0m\n'
if [ "$MYPY_ERRS" -gt 0 ]; then
  printf '  \033[33mmypy: %s error(s) — non-blocking, but report this in the run summary\033[0m\n' "$MYPY_ERRS"
else
  printf '  \033[32mmypy: clean\033[0m\n'
fi

if [ "$FAILED" -ne 0 ]; then
  printf '  \033[31mblocking checks FAILED\033[0m\n'
  exit 1
fi
printf '  \033[32mblocking checks passed\033[0m\n'
