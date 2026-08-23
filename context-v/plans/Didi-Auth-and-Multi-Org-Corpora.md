---
title: "didi.sh Auth and Multi-Org Corpora"
lede: "Log in once, hold several organizations at once, and read one federated corpus across them. Three catches, and two specs that disagree."
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
status: Draft
site_uuid: 3094ab40-f457-48fb-8b10-0649600c35f6
hex_code: 3lubaj
tags:
  - Plan
  - Corpora-Builder
  - Id-Didi-Sh
  - Identity
  - Multi-Tenancy
  - Scoped-Corpora
summary: >-
  The corpora-builder side of didi.sh login, written against the existing
  cross-repo plan rather than replacing it. Adds the three things that plan does
  not cover: didi as source of truth for org membership with a handle as
  identity, reading several organizations' corpora at once, and the
  `parent:child` tag syntax shared by entities and domains. The load-bearing
  finding is that multi-org is a new `CorpusStore` implementation rather than a
  rewrite — which is what the storage seam was built for — and that two specs
  currently disagree about whether organizations and workspaces are one table or
  two.
---

# didi.sh Auth and Multi-Org Corpora

## The spec you asked for

**[[../../../context-v/specs/Id-Didi-Sh-Identity-Service]]** is the canonical
one. It is live: `GET /.well-known/jwks.json` returns 200, `GET /api/me` returns
`{ didi_id, email, name, handle, avatar_url, memberships: [{org_id, role}] }`.

And **the plan already exists**:
[[../../../context-v/plans/Didi-Login-and-Workspace-Config-for-Corpora]]
(2026-08-08, v0.0.0.3), covering login, the device-authorization flow for
desktop, workspace-delivered config, and — the part worth not re-deriving —
**short-lived R2 credentials brokered per workspace**, so no durable bucket key
ever lands on a laptop.

**This plan does not replace it.** It is the corpora-builder half, plus the three
things that plan does not cover.

## Catch 1 — didi as the source of truth on org membership

### The handle already exists. The identity does not.

> *"Orgs and entities will need a handle `[palmer-ai]` and I'm not sure didi has
> that concept yet."*

Half-true, and the half that is missing is the important one.

`organizations` today carries **`id` = canonical email domain** (locked
convention: `lossless.group`, `trychroma.com`), plus a `slug` and a `name`.
`users` already carries a `handle`.

So the *field* exists — `organizations.slug` is the handle. What does not exist
is **the handle being the identity**. `palmer-ai` is not an email domain, and the
reason it cannot be is already recorded in the 2026-08-08 plan, in the operator's
own words: *"I created accounts for palmer-ai with a human.vc email."*

**The change:** promote `slug`/handle to the org's identity; demote the domain to
the same auto-join hint that plan already argues for on workspaces. That is one
more line of an argument already made and signed off, not a new position.

### Two specs disagree about the table

This has to be resolved before "create four orgs" means anything, because the
two specs do not describe the same schema:

| | `Id-Didi-Sh-Identity-Service` | `Flexible-Entity-Relationships` |
|---|---|---|
| shape | separate `organizations` and `workspaces` tables | **one `entities` table** |
| kind | organization is a table | `kind ∈ organization \| workspace \| project`, a **display label with no structural meaning** |
| containment | `workspaces.org_id` is a parent pointer | **"No `parent_id`. No containment. No inheritance of anything, ever."** |

`Flexible-Entity-Relationships` Ruling 1 retracted an earlier containment ruling
on an empirical ground worth repeating: *"projects are collaborations among many
organizations. A project that belongs to one org is the exception."*

**Gate 1 — operator call.** Creating Reach Edu, Humain VC, Palmer AI and
NextLadder means choosing a table. Recommendation: **`entities`**, per the newer
ruling, with `organizations` becoming a view or a `kind`. The identity spec's
`workspaces.org_id` is the containment that ruling withdrew.

### The four, and what NextLadder proves

| handle | corpus |
|---|---|
| `reach-edu` | exists — bucket `reach-edu`, prefix `corpora/`, 832 sources |
| `humain-vc` | exists in augment-it's client stacks |
| `palmer-ai` | exists in augment-it's client stacks |
| `nextladder` | **none, deliberately** |

NextLadder is the useful one. An entity with no corpus proves **entity creation
and corpus provisioning are separate steps** and must stay so — an entity is a
thing you can be a member of before anyone has provisioned a bucket for it. Any
code that assumes `entity ⇒ bucket` breaks on the first one.

The operator is admin in each, which is the normal case rather than a special
one — see the advisor/investor argument the 2026-08-08 plan already settles.

## Catch 2 — several organizations at once

> *"They can select the entities for which they want to view and build corpora …
> Reach Edu, Palmer AI, and NextLadder all will have similar and massively
> overlapping corpora."*

This is the largest change, and the seam already paid for it.

### What assumes one workspace today

| | |
|---|---|
| `WorkspaceResolver.resolve()` | returns **one** `Workspace` |
| `build_store()` | returns **one** `CorpusStore` — one bucket, one prefix |
| `list_sources`, `build_tree`, the manifest, the Pagefind bundle | all take one store |
| `WorkspaceMenu.svelte` | a single-select listbox |
| `/api/meta` | reports one `workspace` |

### The whole change is one new `CorpusStore`

`Storage-Seam.md` justified itself on exactly this kind of substitution — *"what
makes being wrong about R2 cost ~250 lines instead of a rewrite."* This is the
payoff.

A **`FederatedStore(CorpusStore)`** over N workspaces, namespacing every key with
the workspace handle:

```
@reach-edu/live/strategies/workforce-development/sources/a.md
@palmer-ai/live/topics/agent-tooling/sources/b.md
```

`list(prefix)` fans out and concatenates; `read`/`write`/`stat`/`delete` route by
the leading segment. **Everything downstream keeps working unchanged** — browse,
the corpus tree, the manifest, the search bundle — because none of them names a
bucket, which is the invariant the seam was written to hold.

The `@` is deliberate: a bare `reach-edu/` would be indistinguishable from a
folder somebody named `reach-edu`.

### What genuinely has to change

1. **`_domain_of` learns one more strip.** It already strips a leading `live/`
   and a trailing `sources/`; it gains `@<handle>/`. Four lines, and the
   two-layouts-in-the-wild test already covers the shape.
2. **`SourceRow` gains `workspace`** — derived from the key, never stored, the
   same rule the manifest follows for `domain`.
3. **The resolver returns a set.** `resolve()` stays for the write target;
   `available()` lists what the login grants; `selected()` is what the operator
   ticked. Read is the union; **write names exactly one**.
4. **Capture must name its workspace.** With three corpora open, *"file this
   source"* has no default. The API takes a workspace and the form makes it an
   explicit field, not a remembered mode.
5. **Credentials become a set.** N buckets, N short-lived credentials, N
   expiries. The Rust credential client from Phase C holds a map keyed by handle
   and refreshes each independently.
6. **`R2Store` accepts `aws_session_token`** — already named in the 2026-08-08
   plan, unchanged here.

### The overlap is a feature, and it meets the other open work

*"A lot of times a source has broad applications."* Federated, the same URL will
appear under two or three handles — and
[[../issues/Need-Elegant-Resolution-to-Source-Pointers-vs-Master]] has already
established that **`normalized_url` is a usable identity across all 737 filed
sources**, derivable with zero network calls.

Put together, the federated view can say *"this source is in three of your
organizations"* rather than showing it three times. **The multibox and the
multi-org work want the same identity**, which is a strong reason to do the
`normalized_url` backfill first regardless of which lands next.

Note the honest limit: it says a source is *present* in three corpora. It says
nothing about the Extracts, which are per-usage and should differ.

## Catch 3 — `entity:organization` and `domain:strategy`, one pattern

> *"The entities and domains should follow the same pattern `domain:strategy`
> (`domains:strategies`). Parent-Child relationship is not enforced, it is
> derived from the syntax, and can cascade."*

### Most of this already ships

corpora-builder's tags are already `<parent>:<child>` — `strategy:workforce-development`
— and the folder is `strategies/workforce-development/`. Critically, the type
vocabulary is **read from each folder's own `index.md`**, not derived by a rule,
precisely because `strategy`/`strategies` tempts a `+s` and `thesis`/`theses`
breaks it.

That decision pays for this catch for free: **the folder is wherever the
`index.md` is, at any depth.** `entities/organizations/palmer-ai/index.md`
declaring `type: organization, slug: palmer-ai` already works today, with no code
change. Nesting is not a feature to add; it is a consequence of refusing to guess.

"Not enforced, derived from the syntax" is also already the standing ruling:
`Flexible-Entity-Relationships` Ruling 1 — *"`kind` is a display label, carrying
no structural meaning."*

### Three things that are not free

1. **`DomainDef.value` is exactly two segments** — `f"{type}:{slug}"`. A chain
   (`domain:strategy:workforce-development`) needs the value, the parser, the
   filter and the Pagefind filter key to agree on arity. Small, but it is four
   places, and the Pagefind bundle would need rebuilding.
2. **"Cascade" already means something else, next door.** In
   `Flexible-Entity-Relationships` Ruling 2b a cascade is **a credential lending
   act across several entities** — *"a set of loans sharing a `cascade_id`"*,
   declared by a lender, explicitly *not* structural. Here it means the colon
   chain composes through levels. **Same word, adjacent specs, opposite
   emphasis** — one of them has to be renamed before either is written down
   again. Gate 2.
3. **The tuple warning.** That spec says of `user:org:workspace:project`: *"Do
   not store it as a tuple — the copies would disagree."* A `domains:` tag in a
   source file is not the same thing — the file *is* the record, and there is no
   second copy to disagree — but the distinction is thin enough to state out
   loud rather than leave a future reader to infer.
4. **augment-it derives the folder with `` `${type}s` ``.** Per
   [[../issues/Need-Elegant-Resolution-to-Source-Pointers-vs-Master]], its
   `DOMAIN_FOLDERS` table plus a pluralising fallback is the rule this repo
   refuses. A chained syntax makes that fallback wrong more often, so this catch
   lands in augment-it too.

## Phases

Ordered so that each is useful alone and nothing waits on a gate it could have
avoided.

### Phase 0 — decide the schema *(ai-labs, no code)*
Gate 1 (`entities` vs `organizations`+`workspaces`) and Gate 2 (the word
"cascade"). Amend the canonical spec; nothing below starts first. This is Phase A
of the 2026-08-08 plan, with the org-identity and multi-select additions folded
in.

### Phase 1 — `normalized_url` backfill *(corpora-builder, local)*
511 filed sources, no network, reversible. Wanted by the multibox work and by
cross-org overlap alike; the only step here with no didi dependency at all.

### Phase 2 — `FederatedStore` *(corpora-builder, no didi)*
Build and test it against **two local directories**. Multi-org becomes real and
demonstrable before any identity work lands, and the conformance suite the
storage seam already has is what proves it. Includes `_domain_of`, `SourceRow.workspace`,
the multi-select header, and capture's explicit target.

### Phase 3 — didi-side *(Elixir/Phoenix)*
Per the 2026-08-08 plan's Phase B, plus: handle-as-identity, the four entities,
and `GET /api/entities` returning everything the caller may act in, with role.

### Phase 4 — `DidiWorkspaceResolver` *(corpora-builder)*
Implements the existing seam. `StaticWorkspaceResolver` stays for offline and
dev. No call site changes — that is the test of whether the seam held.

### Phase 5 — credential set *(Rust)*
Phase C of the 2026-08-08 plan, holding a map rather than one credential.

## Open questions

1. **Does a chained tag need folder depth to match?** `entity:organization:palmer-ai`
   at `entities/organizations/palmer-ai/` is tidy and doubles the path length.
   Since the folder is read from `index.md`, both work — so this is a convention
   call, not a constraint.
2. **What is the federated key when a workspace has no corpus?** NextLadder has
   no bucket. It should appear as selectable and empty rather than as an error,
   which means `FederatedStore` tolerates a member with no store.
3. **Is `@` right?** It reads well and cannot collide with a folder name. It also
   ends up in every path a user sees.
4. **Cross-org write, ever?** Filing one source into two organizations' corpora
   in one action is the obvious next ask, and it is a different operation from
   the multi-filing inside one corpus that the pointers issue covers.
5. **Offline.** Unchanged from the 2026-08-08 plan's open question 4, and larger
   now: N corpora, N caches.

## Related

- [[../../../context-v/specs/Id-Didi-Sh-Identity-Service]] — the canonical spec
- [[../../../context-v/plans/Didi-Login-and-Workspace-Config-for-Corpora]] — login, device flow, credential brokering; this plan assumes all of it
- [[../../../context-v/specs/Flexible-Entity-Relationships-to-Mirror-Messy-IRL-Collaboration]] — Ruling 1, and the other meaning of "cascade"
- [[../specs/Storage-Seam]] — the seam `FederatedStore` implements
- [[../specs/Strategy-Focus]] — the `type:slug` vocabulary this generalises
- [[../issues/Need-Elegant-Resolution-to-Source-Pointers-vs-Master]] — the `normalized_url` identity both workstreams need
