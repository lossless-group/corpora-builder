---
title: "Need an Elegant Resolution to Source Pointers vs. Master"
lede: "One source, many folders, is the design. But for 75 sources the body sits in an untriaged inbox file the scoped read never reaches."
publish: true
date_created: 2026-08-23
date_modified: 2026-08-23
date_authored_initial_draft: 2026-08-23
date_authored_current_draft: 2026-08-23
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.1.0
status: Open
site_uuid: 666ec300-f412-4ed9-893a-099cc67e6938
hex_code: xu3mtx
tags:
  - Issue
  - Corpora-Builder
  - Source-Curation
  - SurrealDB
  - Scoped-Corpora
---

# Need an Elegant Resolution to Source Pointers vs. Master

## The shape of it

A source can be filed into more than one domain folder. **That is deliberate and
it is the product**: a corpus that will get very large has to hand an agent a
*scoped* set of sources when it drafts, because accuracy and attribution are the
whole point. A source bearing on two strategies belongs in both scopes, with its
own extracts in each.

The mechanism is a small pointer file per folder, with the canonical body kept
elsewhere. What is unresolved is *where elsewhere is*, and today the answer
differs per source.

## What is actually there

Measured across reach-edu on 2026-08-23 — 832 sources, every file parsed:

| | |
|---|---|
| filed in a domain folder | 737 |
| sitting in `live/inbox/` | 95 (80 `pending`, 14 `gated`) |
| carrying a `source_uuid` | 320 |
| distinct `source_uuid`s | 194 |
| filed in **two or more** folders | **79** (126 extra pointers; one source in six) |
| carrying `reference_of` | 28 |
| multi-valued `domains:` | **0** — single-valued by construction, one value per pointer |

And the number that matters most:

| filed sources | `content_pulled` |
|---|---|
| `candidate` | 496 · **false** |
| `metadata-only` | 170 · **false** |
| `fetched` | 71 · true |

**Only 71 of 737 filed sources carry a body.** Meanwhile:

> **80 titles exist both in `live/inbox/` and in a domain folder. In 75 of them,
> the inbox copy is the one holding the real body.**

So for those 75, an agent scoped to a strategy gets identity, lede and an empty
`# Extracts` skeleton — and the actual content is in a file that scoping never
reaches, because `live/inbox/` is not a strategy.

## The two rulings, and why neither is wrong

Two canonicality decisions exist, five weeks apart, about different things:

- **2026-07-25** — [[../../../augment-it/context-v/agent-skills/triage-inbox-w-suggestions/SKILL]]:
  *"the inbox file is canonical — option (a)."* Call the capability so the uuid
  exists, then **merge** the inbox file's body over the metadata-only stub at
  `corpus_path` and delete the inbox original. Reference copies get
  `reference_of` frontmatter.
- **2026-08-02** — [[../../../augment-it/context-v/specs/Source-Content-Storage-SurrealDB-Primary-Local-As-Toggle]]:
  *"SurrealDB is the primary content store."* The body is a `content` field on
  the canonical `sources` row; Extracts live per `source_usages`; `corpus_path`
  becomes **optional**, populated only where a local mirror exists.

They are compatible: the first describes how a capture becomes a filing, the
second says where the bytes ultimately live. **The problem is that neither has
run for these 75.** The merge step never happened, so the inbox file still says
`inbox_status: pending` and still holds the body; and the DB-primary migration is
listed in that spec's own "Still open" as unstarted, across three diverging
copies.

The result is not a wrong design. It is a **half-executed one**, and the half
that is missing is the half that puts content inside a scope.

## What actually hurts, in order

1. **A scoped read is mostly bodyless.** 666 of 737 filed sources have no body
   where the scope can see it. For drafting-with-attribution — the entire
   justification for scoping — that is the issue.
2. **Two ingestion paths produced files for the same URL and nothing reconciled
   them.** `source.add` writes metadata-only stubs into strategy folders; a
   research run wrote fat inbox files carrying `strategy_slugs: [...]`. Both are
   correct on their own terms. The inbox file names the strategies it belongs to
   and never got fanned into them.
3. **`reference_of` is specified and barely used** — 28 files. So a pointer is
   not reliably distinguishable *as* a pointer by reading it; today you infer it
   from `status: metadata-only` and a small byte count.
4. **Duplicated search results**, which is how this surfaced. Cosmetic, and
   explicitly [deferred](../../changelog/2026-08-23_03.md) — flat markdown is
   fast and easy at this size.

## Not the problem

- **The fan-out itself.** 126 extra pointers is ~140KB, and the fan-out is what
  makes a scoped read one `list()` call with no join and no database running.
  That is a feature to preserve in whatever replaces this, not a cost to remove.
- **`multi-valued: 0`.** Read as "multi-domain sources do not exist here" once
  already, and it means the opposite — see
  [[../specs/Strategy-Focus]], corrected 2026-08-23.

## Options, none chosen

1. **Run the triage merge.** Smallest step, no architecture change: for the 75,
   merge the inbox body onto the filed pointer(s), stamp `reference_of` on the
   non-primary copies, delete the inbox original. Leaves the body duplicated
   across N folders — at ~9KB each that is real but not large.
2. **Body in one filing, `reference_of` in the rest.** One folder holds the
   content; siblings point at it. Preserves the one-`list()`-call scope for
   *identity* but not for *content*, so an agent must resolve a pointer.
3. **SurrealDB-primary, as already specified.** Pointers stay thin forever;
   content is fetched by `source_uuid`. Matches the 2026-08-02 decision, and
   costs a running database for what is currently a folder read.
4. **Body beside the corpus, addressed by hash** — the `bin/` pattern this repo
   already uses for PDFs, extended to text. Pointers reference a content-address;
   the bytes exist once; a scoped read is still a folder read plus one fetch.

Option 4 is the one this repo already has machinery for, and it is the only one
that keeps "the corpus is files you can read without our software" true.

## What would make this urgent

An agent drafting from a scoped corpus and citing a source it could not read.
That is reachable today for 666 of 737 filed sources, so the honest statement is
that scoping currently delivers **which sources**, not **what they say**.

## Related

- [[../specs/Strategy-Focus]] — where the `0 multi-valued` misreading was corrected
- [[../specs/Binary-Ingest-And-Bin-Store]] — the content-addressed `bin/` pattern option 4 would extend
- [[../specs/Capture-Link-First]] — the two-tier fetch gate that leaves `content_pulled: false` on purpose
- `../../changelog/2026-08-23_03.md` — where the duplicated results surfaced
