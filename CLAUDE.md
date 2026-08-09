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
uv sync --extra dev            # install

bash scripts/check.sh          # THE LADDER — black, ruff, mypy, pytest, ledger

uv run pytest                  # the suite alone
uv run python scripts/spec_status.py                  # THE LEDGER
uv run python scripts/spec_status.py --spec Capture   # one spec
```

`spec_status.py` exits non-zero when any spec test ID has no implementing test
function. That is deliberate: it makes "I forgot to write that test" a build
failure rather than an oversight.

`check.sh` runs mypy **non-blocking** and prints its error count in the summary.
Report that count in any run summary — a non-blocking check that nobody reads
decays into noise, and printing it in the standard output is the mitigation. If
the count climbs and stays climbed, promote it to blocking.

## Layout

Flat `src/` at the repo root with `src.`-prefixed absolute imports — converged
from `memopop-orchestrator`, whose Rust `SidecarManager` spawns
`.venv/bin/python -m src.server`. Matching it makes the Phase 7 sidecar copy
near-mechanical.

| Path | Purpose |
|---|---|
| `src/ledger.py` | Spec-ID parsing and outcome joining — the loop's bookkeeping |
| `src/store/` | The storage seam — `CorpusStore` ABC, local + R2 implementations |
| `src/model/` | Frontmatter and domain models |
| `src/capture/` | Link-first and file-first capture |
| `src/history/` | Content-addressed objects + checkpoint manifests |
| `src/identity/` | `WorkspaceResolver` seam — static config now, didi.sh at Phase 7 |
| `src/server/` | FastAPI sidecar — Phase 7 |
| `tests/` | Tests, marked with their spec IDs |
| `scripts/` | `spec_status.py` (the ledger), `check.sh` (the ladder) |
| `context-v/` | Living documentation — see the context-vigilance skill |
| `changelog/` | Ship log |
| `app/` | Tauri shell — Phase 7 |

## House style — converged from memopop-ai

Patterns travel knots-style here: copy-from, never a shared package. These are
adopted deliberately, and divergence gets documented rather than invented
silently.

**Doc comments are the strongest shared convention, in both languages.** Module
docstrings explain *why*, cite the governing spec or blueprint, and enumerate
load-bearing rules as a numbered list. Inline comments name the trap. Compare
`memopop-orchestrator/src/curation/source_file.py` (three numbered rules up top)
and `memopop-native/src/lib/stores/sources.svelte.ts` ("No language model
proposes a source — that is the invariant the whole design rests on"). Match
that voice.

| Concern | Convention |
|---|---|
| Layout | flat `src/`, `from src.x.y import z`, relative imports within a package |
| Domain models | **`@dataclass`**, not pydantic — matches `source_file.py` |
| Frontmatter key order | a fixed `FIELD_ORDER` list, never alphabetical, so a diff shows what changed rather than a reshuffle |
| Formatting | **black**, line-length 100, target py311 |
| Linting | ruff, same line length; `E,F,I,UP,B` |
| Types | mypy, `disallow_untyped_defs`, **non-blocking** |
| Versioning | setuptools-scm from git tags (`v0.1.0`) |
| Dev deps | `[project.optional-dependencies] dev` |
| Terminal output | `rich` |
| Tests | `tests/test_<module>.py`, module docstring naming what's covered, section banner comments, `@pytest.mark.parametrize`, everything under `tmp_path` |

**Phase 7 (frontend) inherits from `memopop-native`:** SvelteKit + `adapter-static`
+ Svelte 5 runes, TypeScript with `svelte-check` as the gate,
`src/lib/{transport,stores,components}`, stores named `<name>.svelte.ts`, `$lib/`
alias, PascalCase components. The **transport seam is two methods** —
`request()` / `subscribeEvents()` — and memopop's CLAUDE.md warns against adding
a third casually. Inherit that restraint.

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
