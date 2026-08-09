# Agent instructions for `corpora-builder`

## What this is

A system whose whole job is **building corpora** — capturing, triaging,
fetching, filing, and quality-checking the source material that grounds
everything downstream. Child of the [`ai-labs`](../CLAUDE.md) pseudomonorepo.

Read `../CLAUDE.md` and `../../CLAUDE.md` too — they carry the pseudomonorepo
discipline, the branch tier model, the Chroma RAG, and the HARD STOP relocation
rules that apply here as well.

## This repo runs a loop. Read the loop before working.

**`context-v/loops/Spec-to-Shipped-With-TDD.md` is the operating procedure for
this repo.** It defines the two roles, the seven steps, the gates where you stop
for the operator, and the exit conditions. Load it at the start of any session
that touches specs, plans, or code.

**`context-v/contracts/Autonomy-Gates.md`** states what you may do unattended and
what requires the operator. It is a contract, not a suggestion — the whole point
of this setup is that the operator can leave you running and only return to check
work and make decisions.

Two rules from those documents are important enough to restate here, because
violating either silently destroys the operator's ability to trust an unattended
run:

1. **Never weaken, delete, skip, or rewrite a test to make it pass.** If a spec
   test cannot go green against honest code, the spec is wrong. Stop, switch to
   Lead Product Manager, and surface it. A green suite that was made green by
   editing the suite is worse than a red one.
2. **Never hand-write status.** Spec/test status is *derived* by running
   `uv run python scripts/spec_status.py`. Do not claim a spec is complete;
   run the ledger and report what it says.

## The two roles

| Role | May write | May NOT do |
|---|---|---|
| **Lead Product Manager** | `context-v/explorations/`, `decisions/`, `specs/`, `plans/`, `issues/`, `changelog/` | Write code or tests. Decide anything the operator flagged as theirs. |
| **Lead Engineer** | `core/src/`, `core/tests/`, status flips on plans | Change a spec's intent. Weaken a test. Proceed past a red gate. |

Announce role switches in your response. They are the seams where the operator
re-enters, so making them visible is part of the job.

## The cycle, in one line each

1. **Explore** (`explorations/`) → decisions surface. Sometimes recorded in `decisions/`.
2. **Spec** (`specs/`) → a coherent feature set, *with its natural-language tests enumerated and ID'd*.
3. **Divide** (`plans/`) → only if the spec exceeds one context window.
4. **Implement** (Lead Engineer) → until tests, typecheck, and lint pass.
5. **Operator walk-through** → the human pokes at it.
6. **Issues** (`issues/`) → findings become issue docs + gh issues; repeat 4–6.
7. **Complete** → spec marked complete when the ledger is all-green and no open issue references it.

Changelogs are written at meaningful chunks: a plan landing, a spec completing,
or a group of issues resolving. Not per commit.

## Commands

```bash
cd core

uv sync                                   # install
uv run pytest                             # the suite
uv run pytest -m "spec"                   # only spec-bound tests
uv run ruff check . && uv run ruff format --check .
uv run mypy src

uv run python ../scripts/spec_status.py   # THE LEDGER — derived status per spec
uv run python ../scripts/spec_status.py --spec Capture-Sources   # one spec
```

`spec_status.py` exits non-zero when any spec test ID has no implementing test
function. That is deliberate: it makes "I forgot to write that test" a build
failure rather than an oversight.

## Layout

| Path | Purpose |
|---|---|
| `core/` | The Python package (`corpora`). `uv`-managed. |
| `core/src/corpora/store/` | The storage seam — `CorpusStore` ABC, local + R2 implementations |
| `core/src/corpora/model/` | Frontmatter and domain models |
| `core/src/corpora/capture/` | Link-first and file-first capture |
| `core/src/corpora/history/` | Content-addressed objects + checkpoint manifests |
| `core/tests/` | Tests, marked with their spec IDs |
| `scripts/spec_status.py` | The ledger |
| `context-v/` | Living documentation — see the context-vigilance skill |
| `changelog/` | Ship log |
| `splash/` | GitHub-Pages splash (scaffold pending) |
| `app/` | Tauri shell — not until Phase 7 |

## Skills to load

Always: `context-vigilance` (every `context-v/` write), `git-conventions`
(every commit), `changelog-conventions` (every changelog),
`gh-cli-projects-tasks-conventions` (every gh issue or project item).

When relevant: `pseudomonorepos`, `search-lossless-corpus`, `chroma-local`,
`maintain-design-md` and `theme-system` (Phase 7 surfaces only).

## Language conventions

**Python via `uv`, never bare `pip`.** Type hints everywhere; `mypy` is part of
green. Line length and formatting are `ruff`'s call, not yours — run it rather
than hand-formatting.

## Branch tier

`development` → `main` → `master`, mirrored from the root. Work lands on
`development` unless the operator says otherwise. Never push to `master`.

## Plan of record

`context-v/plans/Corpora-Builder-MVP-R2-Native-With-Checkpoint-History.md` —
the seven phases, the substrate decisions (TARGET / SUBSTRATE / PROVING-CORPUS /
LANGUAGE / HISTORY), and the parked snapshotting-filesystem option with its
re-open trigger.
