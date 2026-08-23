<script lang="ts">
  /**
   * The corpora mark — a leaning stack of paper, seen from the side.
   *
   * Chosen from `src-tauri/icons/drafts/round2` as `24-lean`. The lean is the
   * point: the operator's brief was "a pile of paper that's a bit not straightly
   * aligned", and an upright stack is a ream rather than a pile someone has been
   * working through.
   *
   * TWO LINE COUNTS, ONE SILHOUETTE. Fifteen edges is right at icon size and mud
   * in a header — at 24px they land 1.3px apart and merge into a grey block. The
   * small set is a subsample of the same jittered curve, so the outline, the lean
   * and the top face are identical and only the density changes. A logo that
   * needs a small cut is normal; a logo that is illegible at the size it is
   * actually used is not.
   *
   * COLOUR COMES FROM THE THEME. `--mark-*` are semantic tokens set per mode in
   * tokens.css, so each mode gets a genuinely different treatment rather than one
   * drawing tinted three ways: cool paper with a magenta top sheet in dark, full
   * ink in light (outline art inverts badly — white-on-dark becomes grey-on-white
   * and loses its contrast), and the loud accent plus a real glow in vibrant.
   */
  interface Props {
    /** Rendered px. Below 48 the mark drops to the sparse cut. */
    size?: number;
    title?: string;
  }
  let { size = 24, title = 'corpora' }: Props = $props();

  // [x0, x1, y] per sheet edge, in the 64-unit box.
  const FULL: number[][] = [
    [6.31, 55.38, 20.5],
    [4.0, 58.47, 23.2],
    [5.87, 57.33, 25.9],
    [6.45, 56.89, 28.6],
    [4.18, 59.03, 31.3],
    [6.68, 55.95, 34.0],
    [4.37, 57.38, 36.7],
    [4.04, 57.1, 39.4],
    [5.67, 54.95, 42.1],
    [2.88, 57.77, 44.8],
    [5.34, 55.85, 47.5],
    [5.19, 56.63, 50.2],
    [4.11, 58.6, 52.9],
    [7.1, 56.15, 55.6],
    [4.7, 58.64, 58.3],
  ];
  const SMALL: number[][] = [
    [6.31, 55.38, 22.0],
    [4.0, 58.47, 26.6],
    [5.87, 57.33, 31.2],
    [6.45, 56.89, 35.8],
    [4.18, 59.03, 40.4],
    [6.68, 55.95, 45.0],
    [4.37, 57.38, 49.6],
    [4.04, 57.1, 54.2],
  ];

  const rows = $derived(size >= 48 ? FULL : SMALL);
  const top = $derived(rows[0][2]);
</script>

<svg
  class="mark"
  viewBox="0 0 64 64"
  width={size}
  height={size}
  role="img"
  aria-label={title}
>
  <title>{title}</title>
  <!-- rotate: the lean. About the stack's own middle, so it tips rather than slides. -->
  <g transform="rotate(-4 32 38)" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <!-- The top sheet, in perspective. Without a top face a side-on stack reads
         as a list of rules; with one the eye sees a solid object. -->
    <path
      d="M5 {top} L57 {top} L63 {top - 7} L11 {top - 7} Z"
      fill="var(--mark-top-fill)"
      stroke="var(--mark-top)"
      stroke-width="2"
    />
    {#each rows as [x0, x1, y], i}
      <path
        d="M{x0} {y} L{x1} {y}"
        stroke={i < rows.length / 2 ? 'var(--mark-sheet)' : 'var(--mark-sheet-deep)'}
        stroke-width="1.7"
      />
    {/each}
  </g>
</svg>

<style>
  .mark {
    display: block;
    flex: 0 0 auto;
    /* Vibrant sets a real drop-shadow here; the other two set `none`. */
    filter: var(--mark-glow);
  }
</style>
