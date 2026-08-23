---
version: alpha
name: "Corpora — Labs Theme"
description: >
  The visual contract for corpora-builder's native surface. A dense monospace
  instrument panel wrapped around one reading surface: the operator scans
  hundreds of source titles to decide what to open, so chrome recedes into mono
  and the titles and excerpts alone get a legible sans face. Two-tier tokens,
  two axes (data-theme x data-mode), three modes, per the Lossless theme system.

colors:
  amber-bright: "#f5c971"
  amber-deep: "#3d2c0c"
  amber-ink: "#95621d"
  amber-neon: "#ffd47d"
  amber-void: "#2a1d08"
  amber-wash: "#fbeed1"
  cyan-bright: "#5bbcfb"
  cyan-deep: "#2563a8"
  cyan-loud: "#54c8ff"
  graphite-600: "#646785"
  graphite-700: "#232634"
  graphite-800: "#232634"
  graphite-850: "#1a1d27"
  graphite-900: "#16181f"
  graphite-950: "#0f1115"
  graphite-1000: "#0c0d12"
  halo-100: "#f4ecff"
  halo-400: "#a594c4"
  ink-500: "#686c77"
  ink-900: "#1b1d22"
  magenta-deep: "#9a3fd4"
  magenta-electric: "#c75bfb"
  magenta-loud: "#d96bff"
  mist-100: "#e8eaf0"
  mist-400: "#8a8f9b"
  paper-0: "#ffffff"
  paper-50: "#faf9f6"
  paper-100: "#f1efe9"
  paper-200: "#f4f2ec"
  paper-300: "#ddd9cd"
  paper-400: "#c4bfb0"
  shadow-black: "#000000"
  shadow-ink: "#1b1d22"
  void-600: "#6b5d88"
  void-700: "#16101f"
  void-800: "#3a2a52"
  void-850: "#241934"
  void-900: "#1c1429"
  void-950: "#0c0814"
  void-1000: "#0a0710"

typography:
  body:
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
    fontSize: "13px"
    lineHeight: 1.45
  code:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "12px"
  reading:
    fontFamily: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 600
    letterSpacing: "-0.01em"
  excerpt:
    fontFamily: "{typography.reading.fontFamily}"
    fontSize: "13px"
  meta:
    fontFamily: "{typography.body.fontFamily}"
    fontSize: "11px"

rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  full: "100px"

spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"

components:
  card:
    backgroundColor: "{colors.graphite-700}"
    borderColor: "{colors.graphite-850}"
    borderWidth: "1px"
    rounded: "{rounded.md}"
    padding: "9px 11px"
    typography: "{typography.reading}"
  card-hover:
    borderColor: "{colors.magenta-electric}"
  card-error:
    borderColor: "{colors.amber-bright}"
    textColor: "{colors.amber-bright}"
  chip:
    backgroundColor: "{colors.graphite-1000}"
    borderColor: "{colors.graphite-800}"
    borderWidth: "1px"
    textColor: "{colors.mist-400}"
    rounded: "{rounded.full}"
    padding: "1px 7px"
    typography: "{typography.meta}"
  chip-active:
    backgroundColor: "{colors.magenta-electric}"
    textColor: "{colors.graphite-950}"
  control:
    backgroundColor: "{colors.graphite-900}"
    borderColor: "{colors.graphite-800}"
    borderWidth: "1px"
    rounded: "{rounded.md}"
    padding: "0.35rem 0.5rem"
  button:
    backgroundColor: "{colors.graphite-1000}"
    borderColor: "{colors.graphite-800}"
    rounded: "{rounded.md}"
    padding: "0.35rem 0.7rem"
  viewer:
    backgroundColor: "{colors.graphite-700}"
    borderColor: "{colors.graphite-600}"
    rounded: "{rounded.lg}"
    typography: "{typography.code}"

themes:
  labs:
    description: >
      The ai-labs house theme — electric magenta on near-black, shared with
      augment-it. A didi.sh theme is separate, unstarted work.

modes:
  dark:
    color-background: "{colors.graphite-950}"
    color-surface: "{colors.graphite-700}"
    color-surface-raised: "{colors.graphite-1000}"
    color-field: "{colors.graphite-900}"
    color-border: "{colors.graphite-800}"
    color-border-strong: "{colors.graphite-600}"
    color-text: "{colors.mist-100}"
    color-text-muted: "{colors.mist-400}"
    color-accent: "{colors.magenta-electric}"
    color-accent-2: "{colors.cyan-bright}"
    color-warn-text: "{colors.amber-bright}"
    fx-glow-opacity: 0.25
  light:
    color-background: "{colors.paper-50}"
    color-surface: "{colors.paper-0}"
    color-surface-raised: "{colors.paper-100}"
    color-field: "{colors.paper-200}"
    color-border: "{colors.paper-300}"
    color-border-strong: "{colors.paper-400}"
    color-text: "{colors.ink-900}"
    color-text-muted: "{colors.ink-500}"
    color-accent: "{colors.magenta-deep}"
    color-accent-2: "{colors.cyan-deep}"
    color-warn-text: "{colors.amber-ink}"
    fx-glow-opacity: 0.08
  vibrant:
    color-background: "{colors.void-950}"
    color-surface: "{colors.void-700}"
    color-surface-raised: "{colors.void-1000}"
    color-field: "{colors.void-900}"
    color-border: "{colors.void-800}"
    color-border-strong: "{colors.void-600}"
    color-text: "{colors.halo-100}"
    color-text-muted: "{colors.halo-400}"
    color-accent: "{colors.magenta-loud}"
    color-accent-2: "{colors.cyan-loud}"
    color-warn-text: "{colors.amber-neon}"
    fx-glow-opacity: 0.5
---

# Corpora — Labs Theme

> The runtime source of truth is `app/src/lib/styles/tokens.css`. This document
> is the contract that explains intent, and `node scripts/design-drift.mjs`
> checks the two against each other on every `scripts/check.sh` run.

## Brand & Style

A **dense monospace instrument panel wrapped around one reading surface.** The
operator opens this holding a question — *what do I already have on workforce
development?* — and scans hundreds of cards to decide which to open. Chrome
recedes; titles and excerpts carry the weight.

Everything is bordered. A 1px line at rest, the accent on hover. Nothing is
separated by a shadow that could instead be separated by a rule, and no state
change moves a background — across 845 rows, shifting fills read as noise while a
border that lights up reads as an answer.

**One caveat, found by rendering rather than by reading.** In the dark palette
`--color__graphite-800` and `--color__graphite-700` are the same hex, so a card
drawn as `border: 1px solid var(--color-border)` over `var(--color-surface)`
paints nothing at all. That is augment-it's open gate **A22** — its own
measurement puts `--color-border` at 1.2–1.5:1 against a 3:1 requirement for
control boundaries — and it arrived here with the palette. `--fx-card-border`
therefore points at `graphite-850` in dark: a darker hairline that reads as a
seam and leaves the border available for hover to move. Light and vibrant do not
need the override.

### The architecture is the house one

Per `astro-knots/context-v/blueprints/Maintain-Themes-Mode-Across-CSS-Tailwind.md`
and the `theme-system` skill:

| Layer | What | Example |
|---|---|---|
| 1 — **named palette** | raw values, `__` separator, in `:root` | `--color__magenta-electric` |
| 2 — **theme bindings** | semantic roles per theme × mode | `--color-accent: var(--color__magenta-electric)` |
| 3 — **consumers** | components, reading Tier 2 only | `border-color: var(--fx-card-border-hover)` |

**The visual rule:** see `__` → raw named token. See only `-` → semantic role.
`--fx-*` tokens are semantic tier as well (blueprint §9.2) — they are effects,
not a third naming layer.

**Two axes, not one.** `data-theme` selects the brand; `data-mode` selects
light / dark / vibrant. Collapsing them is how a brand swap turns into a
find-and-replace.

### Three modes, and vibrant is dark-based

Light, dark, vibrant — never two. Dark is the default here because the ai-labs
surfaces are dark-native. **Vibrant inherits from dark, not from light**; the
blueprint names the inverse as the classic error, and the violet-tinted `void`
ramp exists so vibrant has its own near-black rather than borrowing dark's.

The header carries a cycle button rather than a toggle. A two-state toggle
cannot reach a third mode.

### Where the palette came from

Electric magenta on near-black, from `augment-it/packages/theme/theme.css` — the
most built-out surface in ai-labs, and the palette whose contrast pass covers all
108 text-on-surface pairs.

**An earlier version of this file carried navy / cyan / amber** from
`memopop-ai/packages/shared-styles`, on the reasoning that it was the family
brand. It was not: **no shipping app consumes that package.** memopop-native does
not import it despite its CLAUDE.md saying it does — it renders violet out of
~700 hardcoded literals and two locally-reinvented token sets (`--ctl-*` in
`DealWorkspace.svelte`, `--s-*` in `SourceApproval.svelte`). augment-it renders
electric magenta. Both live surfaces are the same violet-magenta family;
shared-styles is a fourth palette nothing draws.

**Converging the didi.sh brand onto this is separate, unstarted work** — which is
why the theme axis exists and why this one is called `labs` rather than being
assumed to be the product's final identity.

## Colors

- **Magenta** is the accent — one saturated element per screen. Electric in dark,
  deep in light, loud in vibrant: one brand colour at three intensities, which is
  the fact Tier 1 exists to be able to state.
- **Cyan** is `--color-accent-2` and `--color-link`.
- **Amber** is **only** for trouble. A card outlined in amber is a source that
  would not parse. Spending it decoratively would cost the interface its one
  alarm.
- **Graphite / paper / void** are the three greyscales, one per mode.

## Typography

**JetBrains Mono is the body face.** That is the family signature — augment-it
describes itself as a dense monospace instrument panel, and everything that is
chrome here matches it: search, filters, chips, counts, URLs, paths, dates.

**`--font-reading` (Inter) is the single exception**, and it is deliberate.
augment-it operates records; this app is *read*. Source titles and excerpts are
prose scanned for meaning across 845 rows, and mono measurably slows that. So the
reading surface gets a sans face and nothing else does.

Role names are descriptive rather than numeric (`--font-body`, `--font-code`,
`--font-reading`), per the blueprint's §2.4 guidance — "heading-1" means nothing
to anyone outside the code.

The scale is narrow: 13px body, 14px titles, 11px metadata. A list of 200 items
carries hierarchy by weight and colour, not by scale. Enlarging titles is the
fastest way to make this screen feel like a feed.

## Layout & Spacing

One column, `max-width: 1100px`, left-aligned rather than centred — the eye
returns to a fixed left edge on every card, which is what makes a long scan
cheap.

The header is sticky and holds the mode cycle, search, the domain filter, and
(when the server is writable) capture. Cards sit in a 6px grid rather than
sharing a list border, so a damaged card can carry its own outline without
disturbing its neighbours.

## Elevation & Depth

Almost flat, and separation comes from **borders rather than elevation**. Cards
carry a barely-there shadow in dark, none worth noticing in light, and a magenta
bloom in vibrant.

Exactly one thing rises: the source viewer, over `--fx-scrim`. That is the only
modal in the app, and its elevation is what says "you are now reading one thing
rather than scanning many."

The scrim is per-mode — 62% black in dark, 38% ink in light, 68% in vibrant. One
value cannot do all three: 45% over a near-black background dims almost nothing,
so the modal stops reading as raised in exactly the mode where it has no shadow
to fall back on.

## Shapes

Three radii and a pill. `sm` (4px) for tight controls, `md` (6px) for cards and
buttons, `lg` (8px) for the viewer, `full` for chips. The ladder tops out at 8px
on purpose — 12px reads as a web card, and this is an instrument.

## Components

### Source card

The workhorse. Title, then the URL or the parse error, then the excerpt, then a
row of chips. The whole card is a button — a 200-row list where only the title is
clickable is a list that fights you. Hover moves the border to the accent; the
fill never changes.

A card whose file would not parse takes `card-error`: amber border, amber title,
the exception in place of the URL. **It is never omitted.** Thirteen sources once
vanished from a count for three weeks, and a browse screen that silently drops
what it cannot read repeats that failure while looking tidier for it.

### Chip

Bordered, pill-shaped, sitting on `--color-surface-raised`, one fact each:
lifecycle status, whether the body was pulled, publication date, domain. A row of
them reads as a row of keys rather than a row of highlights. Only `chip-active`
fills with the accent.

Chips must not read as near-duplicates. Real data caught this: reach-edu carries
strategy-curator's `metadata-only` *status* beside this app's "metadata only"
*pulled* label — two different facts wearing one word. The second is now
`body: yes/no`.

### Control

Inputs, selects and buttons share one shape so the header reads as a single
instrument. Inputs sit on `--color-field`, buttons on `--color-surface-raised`.
Hover moves the border to the accent. Focus is `--focus-ring` — a 2px background
ring plus a 3px accent ring as `box-shadow`, with a real `outline` restored under
`forced-colors`, where `box-shadow` does not survive.

### Viewer

The raw file, monospace, wrapped, in a modal over the scrim. It shows the source
**unmodified** — including frontmatter — because the point of opening one is to
see what is actually on disk.

## Do's and Don'ts

**Do** reference semantic tokens from components. `var(--color-text)`, never
`var(--color__mist-100)`. D1 checks this.

**Do** express state on the border. Hover, focus and error are all border moves
here; a background change across 845 rows is noise.

**Do** keep amber for damage. It is the interface's one alarm.

**Don't** hardcode a colour anywhere below Tier 1 — including inside a shadow. D2
checks this. It is exactly the drift that left `memopop-native` unable to use its
own design system, and it starts with one reasonable-looking `#e5e5e5`.

**Don't** let vibrant inherit light. It is dark-based; that is what the `void`
ramp is for.

**Don't** collapse `data-theme` and `data-mode`. They are independent, and the
didi.sh brand will need the first one free.

**Don't** enlarge card titles to create hierarchy. Weight and colour carry it.

**Don't** add a second modal. The viewer's elevation means "you are reading one
thing now"; a second competing overlay dissolves that meaning.

**Don't** hide a card because it failed to parse. Show it in `card-error` with
its exception. Silence is the failure mode this whole project is built against.
