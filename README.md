# corpora-builder

**Build corpora deliberately — capture, triage, fetch, file, and quality-check the source material that grounds everything downstream.**

`corpora-builder` is a child of the [`ai-labs`](https://github.com/lossless-group/ai-labs) pseudomonorepo. It graduates the corpus-building patterns proven inside [`augment-it`](https://github.com/lossless-group/augment-it) (the "Build Corpora" flow, the corpus inbox, the source-curation gate) and the [context-vigilance](https://www.lossless.group/projects/gallery/context-vigilance) practice into a project of their own — a system whose whole job is assembling trustworthy document corpora that decks, memos, RAG pipelines, and agents can then consume.

## Why this exists

Every serious output The Lossless Group ships — a due-diligence deck, an investment memo, an enriched record set, an agent answer — is only as good as the corpus behind it. Corpus assembly kept reappearing as a sub-feature inside other products (augment-it's corpus inbox and funder corpora, memopop's research inputs, dididecks' substantiation corpora, the Chroma collections behind the Lossless RAG). This repo is where that recurring sub-feature becomes the product.

Per the tree's sharing discipline, corpora-builder does **not** become a shared dependency of the other ai-labs apps — patterns travel knots-style (blueprints + copy-from sample code), not as an npm package the siblings import.

## Status

Early. The design conversation lives in
[`context-v/explorations/Corpora-Builder-System-Design.md`](context-v/explorations/Corpora-Builder-System-Design.md),
which surveys the prior art (augment-it corpus flows, source-curation gate, context-vigilance/Chroma ingest) and sketches the system.

## Layout

| Directory | Purpose |
|---|---|
| `context-v/` | Living documentation — specs, prompts, blueprints, reminders, explorations, issues. See the context-vigilance convention. |
| `changelog/` | Ship log — dated entries of what changed and when. |
| `splash/` | GitHub-Pages splash site for the repo (scaffold pending — see `splash/README.md`). |

## Related work (prior art this project draws on)

- `augment-it/context-v/specs/Corpus-Inbox-Capture-and-Triage.md` — capture-first inbox, triage into corpora
- `augment-it/context-v/specs/Funder-Content-Corpus-Workflow.md` — funder-slug corpora, fetch → file conventions
- `ai-labs/context-v/blueprints/Source-Curation-Gate.md` — human gate between research and corpus admission
- `ai-labs/context-v/explorations/Corpus-Grounded-Generation-of-Decks-and-Memos.md` — the consumption side
- `ai-labs/context-vigilance-kit/` — the Chroma ingest pipeline over the Lossless tree
