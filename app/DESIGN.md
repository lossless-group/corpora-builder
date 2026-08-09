---
version: alpha
name: "Corpora — Lossless Native"
description: >
  The visual contract for corpora-builder's native surface. A dense, quiet
  reading tool: the operator is scanning hundreds of sources to decide what to
  open, so the design gets out of the way of titles and excerpts. Primitives are
  inherited verbatim from memopop-ai's shared-styles so the didi.sh family reads
  as one product; the semantic layer and the dark mode are new here.

colors:
  primary: "#1a3a52"
  primary-50: "#f0f5f8"
  primary-100: "#dae5ed"
  primary-300: "#8fb1c9"
  primary-700: "#112434"
  primary-800: "#0d1925"
  primary-900: "#080e16"
  secondary: "#1dd3d3"
  secondary-400: "#33d7d7"
  accent: "#f59e0b"
  accent-400: "#facc15"
  accent-700: "#b45309"
  neutral-0: "#ffffff"
  neutral-50: "#f8fafc"
  neutral-600: "#64748b"
  neutral-900: "#1a2332"

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
    backgroundColor: "{colors.neutral-0}"
    borderColor: "{colors.primary-100}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
    typography: "{typography.card-title}"
  card-error:
    backgroundColor: "{colors.neutral-0}"
    borderColor: "{colors.accent-700}"
    rounded: "{rounded.md}"
  chip:
    backgroundColor: "{colors.primary-50}"
    textColor: "{colors.neutral-600}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
    typography: "{typography.chip}"
  chip-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.neutral-0}"
    rounded: "{rounded.full}"
  control:
    backgroundColor: "{colors.neutral-0}"
    borderColor: "{colors.primary-100}"
    rounded: "{rounded.sm}"
    padding: "7px 10px"
  viewer:
    backgroundColor: "{colors.neutral-0}"
    borderColor: "{colors.primary-100}"
    rounded: "{rounded.lg}"
    typography: "{typography.mono}"

modes:
  light:
    bg: "{colors.neutral-50}"
    surface: "{colors.neutral-0}"
    ink: "{colors.neutral-900}"
    ink-dim: "{colors.neutral-600}"
    line: "{colors.primary-100}"
    accent: "{colors.primary}"
    warn: "{colors.accent-700}"
  dark:
    bg: "{colors.primary-900}"
    surface: "{colors.primary-800}"
    ink: "{colors.primary-50}"
    ink-dim: "{colors.primary-300}"
    line: "{colors.primary-700}"
    accent: "{colors.secondary}"
    warn: "{colors.accent-400}"
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
`shared-styles`, despite its CLAUDE.md saying it does; its components hardcode
hexes in per-component style blocks. So this file inherits from the *system*, not
from the sibling app's drift — which is the convergence
[[Design-Front-Loading-and-the-Fable-Build-Loop]] asks corpora-builder to lead
rather than follow.

## Colors

Three brand families and a neutral ramp, used for exactly one job each.

- **Primary (navy `#1a3a52`)** is structure: borders, the light-mode accent, and
  every dark-mode surface. It is the colour of the container, never of the
  content.
- **Secondary (cyan `#1dd3d3`)** is attention: focus rings in both modes, and the
  accent in dark mode where navy would disappear into the background.
- **Accent (amber `#f59e0b`)** is **only** for trouble. A card outlined in amber
  is a source that would not parse. Using it decoratively would spend the one
  signal the interface has.
- **Neutrals** carry text and light-mode surfaces.

The two-tier split is the rule that keeps this honest: components reference
semantic tokens (`--ink`, `--surface`, `--line`), never primitives
(`--primary-500`). Switching modes is therefore a remap, not an edit, and a
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

Exactly one thing rises: the source viewer, over a `rgba(0,0,0,.45)` backdrop.
That is the only modal in the app, and its elevation is what says "you are now
reading one thing rather than scanning many".

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

**Do** reference semantic tokens from components. `var(--ink)`, never
`var(--primary-900)`. The two-tier split only pays off if the second tier is the
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
