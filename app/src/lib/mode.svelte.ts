/**
 * Mode switching — light | dark | vibrant.
 *
 * The house contract is THREE modes, not two
 * (`astro-knots/context-v/blueprints/Maintain-Themes-Mode-Across-CSS-Tailwind.md`
 * §1, and the `theme-system` skill). Dark is the default because the ai-labs
 * surfaces are dark-native; vibrant is dark-BASED, which is the error the
 * blueprint calls out by name — letting it inherit light's white background.
 *
 * Two attributes on <html>, two independent axes:
 *   data-theme   which brand. `labs` for now; a `didi` theme is separate work.
 *   data-mode    which mode.
 *
 * Kept deliberately smaller than the blueprint's `ModeSwitcher` class: no
 * Tailwind `dark` class to sync (this app has no Tailwind) and no `mode-change`
 * event, because nothing here listens for one. Add either when something needs it.
 */
export const MODES = ['light', 'dark', 'vibrant'] as const;
export type Mode = (typeof MODES)[number];

const KEY = 'mode';

function stored(): Mode {
  if (typeof localStorage === 'undefined') return 'dark';
  const m = localStorage.getItem(KEY);
  return (MODES as readonly string[]).includes(m ?? '') ? (m as Mode) : 'dark';
}

class ModeState {
  current = $state<Mode>('dark');

  init() {
    this.apply(stored(), true);
  }

  apply(mode: Mode, initial = false) {
    this.current = mode;
    if (typeof document !== 'undefined') document.documentElement.setAttribute('data-mode', mode);
    if (!initial && typeof localStorage !== 'undefined') localStorage.setItem(KEY, mode);
  }

  /** Cycles rather than toggles — a two-state toggle cannot reach a third mode. */
  cycle() {
    this.apply(MODES[(MODES.indexOf(this.current) + 1) % MODES.length]);
  }
}

export const mode = new ModeState();
