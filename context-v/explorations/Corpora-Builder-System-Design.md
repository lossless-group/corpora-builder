---
title: "Corpora-Builder System Design"
lede: "Corpus building has been rebuilt as a sub-feature three times across ai-labs. This exploration surveys what those iterations actually taught us, and sketches the system that deserves its own repo."
date_created: 2026-07-20
date_modified: 2026-07-20
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Fable 5
semantic_version: 0.0.0.1
tags:
  - Exploration
  - Corpus-Building
  - Corpora
  - Context-Vigilance
  - RAG
status: Open
---

# Corpora-Builder System Design

## The question

What is the right shape for a standalone system whose whole job is **building corpora** — capturing, triaging, fetching, filing, and quality-checking the source material that grounds everything downstream (decks, memos, enriched record sets, agent answers, RAG collections)?

More precisely: which of the patterns proven inside [[augment-it]] and the context-vigilance practice graduate into `corpora-builder` as first-class product, which stay behind as app-specific plumbing, and where does this system sit relative to its siblings (augment-it, dididecks-ai, memopop-ai) — given the tree's hard rule that **patterns travel knots-style (blueprint + copy-from sample code), never as a shared package**?

## Why we don't already know

Corpus building inside augment-it exists in **two overlapping generations** that were never reconciled:

- **Generation A — the funder/record-set + pack model** ([[Funder-Content-Corpus-Workflow]]): the aboutness axis. Content files under `corpus/funders/<funder-slug>/`, where the slug is the funder's identity, not the publisher's. Records arrive by CSV upload; packs fire per-record; the operator curates what enters.
- **Generation B — the domain-first curator model** (`corpus.ts` domain functions, the shell's "Build Corpora" flow, the `inbox-curation` agent skill): a generic `(type, slug)` domain — `strategy | thesis | topic | category | market-segment` — each a folder with an `index.md` definition and a `sources/` subdirectory. reach-edu calls domains "strategies", humain-vc calls them "theses"; the backend is fully generic and only the UI pins the noun.

The live reach-edu corpus on disk runs a **three-bucket reconciliation** of both (`clients/reach-edu/corpus/AGENTS.md`), which works but is a truce, not a design. Meanwhile several threads the corpus work depends on all "came due at once" and remain open ([[Two-Clients-One-Flow-Corpora-Auth-and-Deployment-Converge]]): where the corpus substrate lives off-local (R2-native vs host-volume + rclone vs JuiceFS), bucket-per-client isolation, editor/viewer auth, and deployment. The triage layer is largely unbuilt — didi's inbox-triage capability "doesn't exist yet" — and the SurrealDB↔filesystem convergence gap means corpus files carry no `org_slug` link. A fresh repo is the chance to design from what we now know rather than patch the truce.

## What the prior art settled (carry these forward as givens)

These decisions were paid for with real failures and should be treated as constraints, not options:

1. **Files are the truth.** Markdown + YAML frontmatter is the source of truth; databases (SurrealDB, Chroma) index it. Triage is a `git mv` plus a frontmatter edit — the data model stays boring and recoverable by hand ([[Corpus-Inbox-Capture-and-Triage]]).
2. **Verbatim at ingest; never summarize on the way in.** Extraction at ingest is where corruption is born. Derived layers point back at spans ([[Corpus-Grounded-Generation-of-Decks-and-Memos]]).
3. **Two-tier fetch (gated enrichment).** `source.add` writes metadata-only (title + excerpt); `source.fetch` pulls the full body + binary sibling later, explicitly. Discovery stays cheap; grounding cost is spent only on survivors. This generalizes augment-it's origin lesson: gate every enrichment step — bulk AI enrichment going haywire is what created the product.
4. **The source-curation gate is per-object and pre-generation.** A human prune/rank/provenance-stamp step sits between retrieval and generation. Triage per-URL post-generation produced a 99.7% reject rate in OfficialPulse; the unit of work was the bug ([[Source-Curation-Gate]]).
5. **Aboutness over publisher.** The filing slug answers "who/what is this *about*", not "who published it". Tags (`strategy_slugs`, Train-Case-free but dash-enforced, casing preserved) carry many-to-many membership; a strategy is *reconstructed by query*, never by nesting.
6. **Extracts live in the body as LFM directives, never mirrored into YAML.** Quote text breaks YAML; the `remark-directive` parse *is* the structured extraction, so there is no mirror to drift.
7. **The inbox is capture-first staging, not a corpus.** Immutable `captured_*` fields, null-until-triage `triaged_*` fields, and a second-pass requirement. It is also the *richest* bucket, not a cleanup queue — the reach-edu quality scan treated 140 inbox files as first-class inventory ([[First-Pass-Corpus-Quality-Scan-for-reach-edu]]).
8. **Binaries ride alongside.** PDFs are downloaded as siblings (sha256, size, content-type in a `binary_asset` block; git-lfs; Ghostscript compression over 3MB) because Jina text loses citable page/figure fidelity and remote URLs rot ([[Download-PDFs-into-Corpus-Inbox]]).
9. **Consumption is a separate pipeline.** Chroma ingest runs with content-hash change detection, stable IDs, per-kind collections, and set-diff GC ([[Track-and-Ingest-Lossless-Content-into-Chroma]]). The corpus is INPUT; decks and memos are produced elsewhere.
10. **Client data is the privacy boundary.** Client-private content stays in per-client repos/scopes; only patterns, specs, and skills get lifted into public context-v.

## The open design tensions

### Tension 1 — What *is* corpora-builder: app, harness, or discipline?

**Option A — A standalone app** (fourth sibling): its own UI (inbox, curation gate, quality dashboard), its own storage, its own didi surface. Pro: the corpus finally gets a front door that isn't borrowed from a CSV-enrichment product. Con: immediately re-raises the auth/deployment/substrate threads, and risks becoming augment-it-minus-records.

**Option B — A reference implementation + blueprint kit**: the canonical `corpus.ts`-descended domain model, the `source.*` verb vocabulary, the frontmatter schemas, the quality-scan scripts — shipped as copy-from sample code the siblings adopt knots-style. Pro: honors the no-shared-dependency rule perfectly; cheapest path to unifying Generations A and B. Con: no operator surface of its own; the pattern only lives where someone copies it.

**Option C — A corpus *service* with thin surfaces** (the augment-it workspace stance applied here): a thin orchestrator over domain services that own their data, with chat-verb and microfrontend surfaces mounted *into* the sibling apps rather than a monolithic app of its own. Pro: matches the deliberately-small-remotes thesis; didi's `source.*` verbs already assume this shape. Con: "service shared by three apps" flirts with the shared-dependency prohibition and needs a careful contract (verbs + file formats, not imported code).

### Tension 2 — Reconciling Generation A and Generation B

The domain-first model (B) is the more general substrate — a funder is arguably just a domain of type `funder` (or the aboutness tag on sources within other domains). But record-set lineage (`record_uuid` surviving promotions) is load-bearing for augment-it and shouldn't be forced into the generic model. Leaning: corpora-builder's canonical model is **domain-first with funders as a domain type**, and record-set lineage remains an augment-it-side concern that *points into* the corpus rather than shaping it.

### Tension 3 — Where the corpus lives

Local filesystem + per-client git worked for two clients; it does not survive cloud deployment, multi-operator editing, or didi-in-the-browser. The unresolved substrate question (R2-native vs volume + rclone vs JuiceFS) belongs to *this* repo now. Whatever is chosen must preserve constraint 1 (files-as-truth, hand-recoverable) — which argues against anything that makes the object store the primary and the files a cache.

### Tension 4 — How much of context-vigilance is the same system?

Corpus building **is** context-vigilance applied to client source material: same frontmatter-as-truth, same wikilinks, same Chroma read-side. The context-vigilance-kit ingest scripts and the client-corpus ingest are near-twins. Should corpora-builder subsume the ingest side of the kit, or stay a sibling that shares conventions? Leaning: share conventions and the collection-naming scheme; do not merge repos — the kit serves the Lossless tree, corpora-builder serves client corpora, and the privacy boundaries differ.

## Tentative direction

Start with **Option B shading into C**: make this repo the canonical home of the unified domain model, frontmatter schemas, `source.*` verb vocabulary, inbox/triage lifecycle, and quality-scan tooling — as documented blueprint + runnable reference code — and only then grow the thin service/surfaces where a real engagement demands them. That sequencing mirrors how augment-it itself was built (workspace before chat) and defers the substrate/auth threads until there's a concrete consumer.

First concrete artifacts to produce from this exploration:

1. A **spec** for the unified corpus domain model (Generation A ⊎ B reconciliation, frontmatter schemas as the contract).
2. A **blueprint** for the corpus lifecycle (capture → triage → fetch → file → quality-scan → ingest), lifted from the prior art but app-agnostic.
3. The **quality-scan script** generalized from the reach-edu first-pass scan into a re-runnable, corpus-agnostic tool — the first runnable thing this repo ships.

## Outcome

Open. Ends when the domain-model spec is written and signed off.

## Related

- [[Funder-Content-Corpus-Workflow]] — augment-it spec, Generation A
- [[Corpus-Inbox-Capture-and-Triage]] — augment-it spec, capture-first inbox
- [[Download-PDFs-into-Corpus-Inbox]] — binary-sibling discipline
- [[First-Pass-Corpus-Quality-Scan-for-reach-edu]] — the quality-scan prior art
- [[Source-Curation-Gate]] — ai-labs blueprint, the per-object human gate
- [[Corpus-Grounded-Generation-of-Decks-and-Memos]] — the consumption side
- [[Two-Clients-One-Flow-Corpora-Auth-and-Deployment-Converge]] — the open substrate/auth/deployment threads
- [[Track-and-Ingest-Lossless-Content-into-Chroma]] — the Chroma read-side pipeline
