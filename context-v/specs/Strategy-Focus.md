---
title: "Strategy Focus"
lede: "\"Mainly look here\" is emphasis, not membership. Focusing a strategy reorders the corpus; it never hides the rest of it."
publish: true
date_created: 2026-08-22
date_modified: 2026-08-22
date_authored_initial_draft: 2026-08-22
date_authored_current_draft: 2026-08-22
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5 (1M context)
at_semantic_version: 0.0.1.0
status: Draft
site_uuid: 2e7b4c96-8a01-4d3f-b25e-6c9f0a17d834
hex_code: t8pv2c
tags:
  - Spec
  - Corpora-Builder
  - Navigation
  - Retrieval
  - Frontend
---

# Strategy Focus

## Why

Every source in reach-edu belongs to the client. When someone sits down to draft
a strategy document or a presentation, they want **all** of it available — and a
pointer that says *mainly look here*.

That is what the `domains:` frontmatter field is:

```yaml
domains:
  - "strategy:adult-literacy-numeracy"
```

Measured across all 845 sources on 2026-08-22:

| | |
|---|---|
| carry a `domains:` list | 241 |
| carry none | 604 |
| multi-valued | **0** |
| disagreeing with their own folder | **0** |
| prefixes in use | `strategy` (223), `topic` (18) |

**Read that table as a pointer, not as a half-finished taxonomy.** A source with
no `domains:` is not unclassified; it is simply not the first place to look for
any particular strategy. Backfilling the 604 would destroy the signal by making
everything equally emphasised — which is why this spec does not.

## The one rule everything follows from

**Focus orders. It never excludes.**

The corpus filter already in the app is exclusive: pick
`strategies/workforce-development` and the other 591 sources vanish. That is the
right behaviour for *filtering* and exactly the wrong behaviour here, because
it removes the access the tag exists to preserve. Both mechanisms stay; they are
different verbs.

The count reflects it: **"82 to start with, 832 available"**, never "82 sources".

## Behaviours

### 1. The tag is searchable text

Typing `literacy` reaches a source carrying `strategy:adult-literacy-numeracy`
even when neither its title nor its excerpt contains the word. The tag is part of
what a source *says about itself*, so search treats it that way.

### 2. Focus reorders, and reports both numbers

`focus=strategy:workforce-development` returns the whole listing with the
emphasised sources first, plus `focused_total` beside `total`.

### 3. The type vocabulary is read from the corpus, never assumed

**This is the load-bearing decision.** The types are open: reach-edu declares
`strategy` and `topic`; another client uses `thesis`. There is no rule that maps
a tag to a folder across that. `strategy`/`strategies` tempts a `+s` —
**`thesis`/`theses` breaks it on the first try**, and whatever replaces the rule
breaks on the client after that.

Each domain already states the answer, in the `index.md` sitting in its folder:

```yaml
type: "strategy"
slug: "adult-literacy-numeracy"
title: "Adult Literacy & Numeracy"
```

So the join is read: nine reads in reach-edu, one per declaration, not one per
source. That also supplies the human label for the toggle — *Adult Literacy &
Numeracy*, not `adult-literacy-numeracy` — and makes **nesting free**, because
the folder is wherever the `index.md` is, at any depth.

A folder with no `index.md` is not a focus. Nothing is invented for it.

### 4. Ordering is partitioned on the key

The whole corpus is ordered without opening a file, the same trick `list_domains`
and the corpus tree use.

**With a stated limit.** This is exact today because all 241 tagged sources sit
in the folder their tag names, and none carries a second tag. **The day a source
under `funders/gates-foundation/` is tagged `strategy:workforce-development`,
key-partitioning will miss it** — the tag lives inside the file, and finding it
across the corpus means 845 reads, which is the 20.6-second cold start that made
the window look hung.

The fix is an index, not brute force: a small manifest written on capture and on
re-tag, the same instinct as the `bin/` pointer. It is **not built**, and this
paragraph exists so nobody discovers the limit from a wrong answer. What *is*
already correct: any row the listing actually reads is matched on its real
`domains:` value, so search and the rendered order honour the tag even where
partitioning could not see it.

### 5. Multiple focuses are the eventual shape, one is the current one

`domains:` is a list. One focus at a time is what ships; the API takes a single
`focus` because inventing multi-focus ranking with zero multi-valued data would
be designing against imagination.

### 6. A declaration is not a source

`index.md`, `AGENTS.md` and `README.md` describe the corpus rather than being
captured material, and are excluded from the listing. Thirteen such files in
reach-edu were being rendered with no URL and `status: candidate` —
indistinguishable from a source we found and never fetched — and inflating the
count. `845 sources` was 832 sources plus 13 documents *about* them.

This stopped being cosmetic the moment `index.md` became the file that supplies
the type vocabulary. The document that names a domain cannot also be listed as
one of its unprocessed leftovers.

## Tests

| ID | Given / When / Then |
|---|---|
| `FOCUS-01` | Given a source whose `domains:` names a strategy, when a word from that tag is searched, then the source matches even though its title and excerpt do not contain it |
| `FOCUS-02` | Given a corpus with sources inside and outside a strategy, when that strategy is focused, then every source is still returned and the focused ones come first |
| `FOCUS-03` | Given a focus, when the listing is returned, then `focused_total` counts the emphasised sources and `total` still counts them all |
| `FOCUS-04` | Given a corpus declaring an unfamiliar type (`thesis`, whose plural no rule would guess) and a nested one, when the focuses are derived, then both resolve from their own `index.md` and a folder without one is not offered |
| `FOCUS-05` | Given a focus and a page smaller than the focused set, when the first page is requested, then it holds only focused sources — the ordering is not undone by the date sort |
| `FOCUS-06` | Given no focus, when the listing is returned, then order and `focused_total` are unchanged from before this feature |
| `FOCUS-07` | Given a source tagged into a strategy whose folder it does not live in, when that strategy is focused and the row is read, then the row still sorts as focused |
| `FOCUS-08` | Given a nested, unfamiliar type, when it is focused, then it orders exactly like a familiar one, with no code that knows its name |

## Related

- `context-v/specs/Browse-Corpus.md` — the listing this extends, and `BROWSE-17`, the stale-response guard search needed once a search cost 5.8s
- `context-v/specs/Domain-Navigation.md` — the *exclusive* verb, deliberately kept separate
- `context-v/specs/Corpus-Tree.md` — the same keys-not-bodies discipline
