---
version: alpha
name: "Corpora — Lossless Native"
description: >
  The visual contract for corpora-builder's native surface. A dense, quiet
  reading tool: the operator is scanning hundreds of sources to decide what to
  open, so the design gets out of the way of titles and excerpts. Primitives are
  inherited verbatim from memopop-ai's shared-styles so the didi.sh family reads
  as one product; the semantic layer and the dark mode are new here. Token
  vocabulary is augment-it's, so components move between the two repos unedited.

colors:
  navy-50: "#f0f5f8"
  navy-100: "#dae5ed"
  navy-300: "#8fb1c9"
  navy-500: "#1a3a52"
  navy-700: "#112434"
  navy-800: "#0d1925"
  navy-900: "#080e16"
  cyan-400: "#33d7d7"
  cyan-500: "#1dd3d3"
  amber-400: "#facc15"
  amber-500: "#f59e0b"
  amber-700: "#b45309"
  slate-0: "#ffffff"
  slate-50: "#f8fafc"
  slate-600: "#64748b"
  slate-900: "#1a2332"
  slate-1000: "#000000"

typography:
  sans:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14.5px"
    lineHeight: 1.55
  title:
    fontFamily: "{typography.sans.fontFamily}"
    fontSize: "14.5px"
    fontWeight: 620
    letterSpacing: "-0.01em"
  card-title:
    fontFamily: "{typography.sans.fontFamily}"
    fontSize: "14.5px"
    fontWeight: 580
  meta:
    fontFamily: "{typography.sans.fontFamily}"
    fontSize: "12.5px"
  chip:
    fontFamily: "{typography.sans.fontFamily}"
    fontSize: "11.5px"
  mono:
    fontFamily: "'JetBrains Mono', ui-monospace, Menlo, monospace"
    fontSize: "12.5px"

rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
  full: "100px"

spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"

components:
  card:
    backgroundColor: "{colors.slate-0}"
    borderColor: "{colors.navy-100}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
    typography: "{typography.card-title}"
  card-error:
    backgroundColor: "{colors.slate-0}"
    borderColor: "{colors.amber-700}"
    rounded: "{rounded.md}"
  chip:
    backgroundColor: "{colors.navy-50}"
    textColor: "{colors.slate-600}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.chip}"
  chip-active:
    backgroundColor: "{colors.navy-500}"
    textColor: "{colors.slate-0}"
    rounded: "{rounded.full}"
  control:
    backgroundColor: "{colors.slate-0}"
    borderColor: "{colors.navy-100}"
    rounded: "{rounded.sm}"
    padding: "7px 10px"
  viewer:
    backgroundColor: "{colors.slate-0}"
    borderColor: "{colors.navy-100}"
    rounded: "{rounded.lg}"
    typography: "{typography.mono}"

modes:
  light:
    color-background: "{colors.slate-50}"
    color-surface: "{colors.slate-0}"
    color-text: "{colors.slate-900}"
    color-text-muted: "{colors.slate-600}"
    color-border: "{colors.navy-100}"
    color-accent: "{colors.navy-500}"
    color-warn-text: "{colors.amber-700}"
    fx-scrim: "45% {colors.slate-1000}"
  dark:
    color-background: "{colors.navy-900}"
    color-surface: "{colors.navy-800}"
    color-text: "{colors.navy-50}"
    color-text-muted: "{colors.navy-300}"
    color-border: "{colors.navy-700}"
    color-accent: "{colors.cyan-500}"
    color-warn-text: "{colors.amber-400}"
    fx-scrim: "62% {colors.slate-1000}"
---

# Corpora — Lossless Native

> The runtime source of truth is `app/src/lib/styles/tokens.css`. This document
> is the human- and agent-readable contract that explains intent. Keep the two in
> sync when either changes.

## Brand & Style

This is a **reading tool that happens to write**. The operator opens it holding a
question — *what do I already have on workforce development?* — and scans
hundreds of cards to decide which one to open. Everything here serves that scan:
titles carry the weight, excerpts get real room, and chrome recedes.

The register is quiet and dense, closer to a well-set bibliography than to a
dashboard. No gradients, no illustration, no motion. The only saturated colour in
the interface is the accent, and it appears on roughly one element per screen.

**Where the palette came from matters.** The primitives are copied verbatim from
`memopop-ai/packages/shared-styles` — the same navy, the same cyan, the same
amber, Inter and JetBrains Mono. corpora-builder is the fourth surface in the
didi.sh family and should not read as a stranger.

It is worth recording that `memopop-native` itself does **not** consume
`shared-styles`, despite its CLAUDE.md saying it does; its components carry ~700
colour literals and reinvent a fragment of a token system twice, locally and
under two different names (`--ctl-*` in `DealWorkspace.svelte`, `--s-*` in
`SourceApproval.svelte`). So the primitives here come from the *system*, not from
the sibling app's drift.

### The names are augment-it's; the palette is not

[[Design-Front-Loading-and-the-Fable-Build-Loop]] asked whether corpora-builder
could be "the reference the sibling design systems converge toward," on the
premise that the siblings were "probably messy if not total chaos." **That
premise was measured on 2026-08-22 and holds for memopop-native and not for
augment-it**, which carries an eleven-rule federated contract, a drift script, a
`@property` fallback layer, three modes, and contrast verified across all 108
text-on-surface pairs. It is the only real design system in ai-labs. A 17-member
system with a checker does not converge toward a one-page app.

So this file converges **on the vocabulary** and holds its own palette:

| | source | why |
|---|---|---|
| Tier-1 / Tier-2 token names, `__` separator, `data-mode` | augment-it | the vocabulary is the interface — patterns travel this tree by copy-from, and a component cannot be copied across a rename |
| navy / cyan / amber, Inter + JetBrains Mono | memopop shared-styles | the didi.sh family's brand; augment-it is magenta on near-black in monospace, and a different product |

The split is the point. **Names are the portable part, hue is the brand part.**
Taking both would have repainted a reading tool to settle a naming question;
taking neither leaves every shared component one find-and-replace away from
working.

Where corpora-builder can still lead: augment-it's frontmatter registers 17
member `DESIGN.md` files and two exist. Its federal layer is far ahead of this
one; its local layer is unwritten, and *this document* is the shape that fills
it.

## Colors

Three brand families and a neutral ramp, used for exactly one job each.

- **Navy (`#1a3a52`)** is structure: borders, the light-mode accent, and
  every dark-mode surface. It is the colour of the container, never of the
  content.
- **Cyan (`#1dd3d3`)** is attention: focus rings in both modes, and the
  accent in dark mode where navy would disappear into the background.
- **Amber (`#f59e0b`)** is **only** for trouble. A card outlined in amber
  is a source that would not parse. Using it decoratively would spend the one
  signal the interface has.
- **Slate** carries text and light-mode surfaces.

The two-tier split is the rule that keeps this honest: components reference
semantic tokens (`--color-text`, `--color-surface`, `--color-border`), never
primitives (`--color__navy-500`). Switching modes is therefore a remap, not an edit, and a
component's stylesheet is checkably free of raw colour.

## Typography

**Inter** for everything read as language; **JetBrains Mono** for everything read
as data — the raw source file in the viewer, and file paths.

The scale is deliberately narrow: 14.5px body, 12.5px metadata, 11.5px chips.
Card titles sit at body size with weight 580 rather than a larger size, because a
list of 200 items needs its hierarchy carried by weight and colour, not by scale.
Enlarging titles is the fastest way to make this screen feel like a blog.

## Layout & Spacing

A single column, `max-width: 1100px`, left-aligned rather than centred — the eye
returns to a fixed left edge on every card, which is what makes a long scan
cheap.

The header is sticky and holds search, the domain filter, and (when the server is
writable) capture. Everything else scrolls. Cards are separated by 9px in a grid
rather than by borders on a shared list, so a damaged card can carry its own
outline without disturbing its neighbours.

Spacing follows the shared-styles scale (`0.25 / 0.5 / 1 / 1.5 / 2rem`), applied
loosely. This is a dense surface; generous vertical rhythm would halve how many
sources fit on a screen.

## Elevation & Depth

Almost flat. Cards carry a barely-there shadow in light mode and **none at all in
dark**, where a shadow reads as mud rather than lift; separation there comes from
surface lightness against the background.

Exactly one thing rises: the source viewer, over the `--scrim` backdrop. That is
the only modal in the app, and its elevation is what says "you are now reading
one thing rather than scanning many".

The scrim is **per-mode**: 45% black in light, 62% in dark. One value cannot do
both jobs — 45% over a `#080e16` background dims almost nothing, so the modal
stops reading as raised in exactly the mode where it has no shadow to fall back
on. It carried a literal `rgba(0,0,0,.45)` in the component until 2026-08-22,
which is the whole reason nobody noticed.

## Shapes

Four radii, each with a job. `sm` (6px) for controls, `md` (8px) for cards, `lg`
(12px) for the viewer, `full` for chips. The progression is deliberate: the
larger the surface, the softer the corner, so scale reads as hierarchy without
any change in colour.

## Components

### Source card

The workhorse. Title, then the URL or the parse error, then the excerpt, then a
row of chips. The whole card is a button — a 200-row list where only the title is
clickable is a list that fights you.

A card whose file would not parse takes `card-error`: amber border, amber title,
the exception in place of the URL. **It is never omitted.** Thirteen sources once
vanished from a count for three weeks, and a browse screen that silently drops
what it cannot read repeats that failure while looking tidier for it.

### Chip

Small, pill-shaped, one fact each: lifecycle status, whether the body was pulled,
publication date, domain. Only `chip-active` (filled with the accent) draws the
eye, and only for a promoted source.

Chips must not read as near-duplicates. Real data caught this: reach-edu carries
strategy-curator's `metadata-only` *status* beside this app's "metadata only"
*pulled* label — two different facts wearing one word. The second is now
`body: yes/no`.

### Control

Inputs, selects, and buttons share one shape so the header reads as a single
instrument rather than three widgets. Focus is a 2px cyan ring at 2px offset, on
every mode.

### Viewer

The raw file, monospace, wrapped, in a modal over a dim backdrop. It shows the
source **unmodified** — including frontmatter — because the point of opening one
is to see what is actually on disk.

## Do's and Don'ts

**Do** reference semantic tokens from components. `var(--color-text)`, never
`var(--color__navy-900)`. The two-tier split only pays off if the second tier is the
only one components touch.

**Do** keep amber for damage. It is the interface's one alarm; spending it on
decoration leaves nothing to say "this file is broken".

**Don't** hardcode a hex in a component style block. That is precisely the drift
that left `memopop-native` unable to use its own design system, and it starts
with one reasonable-looking `#e5e5e5`.

**Don't** enlarge card titles to create hierarchy. Weight and colour carry it.
Scale changes turn a dense scanning surface into a feed.

**Don't** add a second modal. The viewer's elevation means "you are reading one
thing now"; a second competing overlay dissolves that meaning.

**Don't** hide a card because it failed to parse. Show it in `card-error` with
its exception. Silence is the failure mode this whole project is built against.
