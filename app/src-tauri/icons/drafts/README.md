# App icon drafts — stop-gap

Dark-mode values are hardcoded here on purpose: this is a look-at stage, and
committing to the theme tokens before a mark is chosen would mean doing the
three-mode work three times.

**Whichever wins gets re-cut against `app/src/lib/styles/tokens.css`** so it
holds in light and vibrant — `--color-text` for the top sheet, `--color-border-strong`
and `--color-text-muted` for the sheets behind, `--color-accent` where a draft
uses one. An SVG in the app can inherit via `currentColor`; a `.icns`/`.ico` for
the dock cannot, so the packaged icon needs one baked palette and dark is the
right one to bake.

Rendered contact sheet: `contact-sheet.html` (open it, or re-render headless).
