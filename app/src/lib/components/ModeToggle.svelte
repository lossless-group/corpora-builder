<script lang="ts">
  /**
   * One icon, the current mode, click to advance — `context-v/specs/Header-Chrome.md`.
   *
   * The three glyphs (sun, crescent, four-point star) are lifted verbatim from
   * `ai-labs/splash/src/components/ModeToggle.astro`, where the same three modes
   * carry the same three marks. Pattern port, not a shared dependency.
   *
   * Splash pages show ALL THREE and glow the active one. Here it is a straight
   * swap. A three-button group is right on a marketing page where the modes are
   * part of the pitch; in a dense tool it is three targets to do one thing.
   *
   * The tooltip is what makes one icon honest — `modeTooltip` names the mode you
   * are in and the one a click produces, generated from the cycle so the two
   * cannot disagree.
   */
  import { mode } from '$lib/mode.svelte';
  import { modeTooltip } from '$lib/modes';
</script>

<button
  type="button"
  class="mode-toggle"
  title={modeTooltip(mode.current)}
  aria-label={modeTooltip(mode.current)}
  onclick={() => mode.cycle()}
>
  {#if mode.current === 'light'}
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  {:else if mode.current === 'dark'}
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  {:else}
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <path d="M12 2l2.39 4.84L20 8l-4 3.9.94 5.5L12 14.77 7.06 17.4 8 11.9 4 8l5.61-1.16L12 2z" />
    </svg>
  {/if}
</button>

<style>
  .mode-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 26px;
    padding: 0;
    flex: 0 0 auto;
    color: var(--color-text-muted);
    background: transparent;
  }
  .mode-toggle:hover { color: var(--color-accent); }
</style>
