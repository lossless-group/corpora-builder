/**
 * The three-mode cycle and its labels — `context-v/specs/Header-Chrome.md`.
 *
 * Plain module, no runes, so the rules can be tested by `node --test` without a
 * Svelte compiler. `mode.svelte.ts` holds the reactive state and imports these;
 * same split as `domains.ts` under the domain combobox — the part worth testing
 * is separated from the part that needs a component to exist.
 */
export const MODES = ['light', 'dark', 'vibrant'] as const;
export type Mode = (typeof MODES)[number];

/** The mode a click produces. The cycle, stated once. */
export function nextMode(current: Mode): Mode {
  return MODES[(MODES.indexOf(current) + 1) % MODES.length];
}

const TITLE: Record<Mode, string> = { light: 'Light', dark: 'Dark', vibrant: 'Vibrant' };

/**
 * What the toggle promises: the mode you are in, and the one a click gets you.
 *
 * A single icon that changes on click without saying what it becomes is a
 * guessing game — the cost of showing one glyph where the splash pages show
 * three. Generated from `nextMode` rather than written out, so the label cannot
 * drift from the cycle it describes.
 */
export function modeTooltip(current: Mode): string {
  return `${TITLE[current]} mode · click for ${TITLE[nextMode(current)]}`;
}

export function isMode(value: unknown): value is Mode {
  return typeof value === 'string' && (MODES as readonly string[]).includes(value);
}
