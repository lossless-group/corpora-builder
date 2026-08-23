<script lang="ts">
  /**
   * The results panel that drops out of the search box.
   *
   * Modelled on `context-vigilance-kit/splash`, whose compact search is a
   * popover under the input rather than a filter on a list further down the
   * page. Its result card is the shape being copied: **title, tags, and the
   * content that matched** — three things, in that order.
   *
   * Filtering the list below is not the same affordance. The list answers "show
   * me everything matching, so I can work through it"; this answers "did the
   * thing I am thinking of come back", without leaving the box you are typing
   * in. Both are wanted; only one of them existed.
   *
   * It renders from ROWS, not from Pagefind, deliberately: a corpus with no
   * search index is the common case today, and a panel that only appeared once
   * somebody ran `reindex` would look broken rather than unindexed. With an
   * index the same rows arrive ranked and their excerpts arrive marked, so the
   * panel gets better without changing.
   */
  import type { SourceRow } from '$lib/api';

  interface Props {
    rows: SourceRow[];
    /** key → the passage that matched, with `<mark>` on the terms. Empty when
     *  the corpus has no search index; the row's own excerpt stands in. */
    marks: Map<string, string>;
    total: number;
    /** How many the panel shows before deferring to the list below. */
    limit?: number;
    ranked: boolean;
    tagLabel: (value: string) => string;
    onpick: (row: SourceRow) => void;
    onclose: () => void;
  }
  let {
    rows,
    marks,
    total,
    limit = 8,
    ranked,
    tagLabel,
    onpick,
    onclose
  }: Props = $props();

  const shown = $derived(rows.slice(0, limit));

  function onKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape') onclose();
  }

  $effect(() => {
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
</script>

<div class="panel" role="listbox" aria-label="Search results">
  {#if !shown.length}
    <p class="empty">Nothing matches.</p>
  {:else}
    <ul>
      {#each shown as row (row.path)}
        <li>
          <button class="hit" role="option" aria-selected="false" onclick={() => onpick(row)}>
            <div class="t">{row.title || row.path.split('/').pop()}</div>
            {#if marks.has(row.path)}
              <!-- The passage that matched. Already reduced to text plus
                   <mark> by `safeExcerpt`. -->
              <div class="e">{@html marks.get(row.path)}</div>
            {:else if row.excerpt}
              <div class="e">{row.excerpt}</div>
            {/if}
            {#if row.domains.length}
              <div class="tags">
                {#each row.domains as d (d)}<span class="tag">{tagLabel(d)}</span>{/each}
              </div>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
    <p class="foot">
      {#if total > shown.length}
        {shown.length} of {total} — the rest are in the list below
      {:else}
        {total} result{total === 1 ? '' : 's'}
      {/if}
      {#if !ranked}
        <span class="dim">· unranked</span>
      {/if}
    </p>
  {/if}
</div>

<style>
  .panel {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    right: 0;
    z-index: 40;
    max-height: 62vh;
    overflow-y: auto;
    background: var(--color-surface-raised);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    box-shadow: var(--fx-card-shadow);
  }
  ul { list-style: none; margin: 0; padding: 4px; }
  li { margin: 0; }
  /* Rows opt OUT of the global control primitive — 8 bordered, filled buttons
     read as a form, not as results. Same rule the corpus tree follows. */
  .hit {
    display: block;
    width: 100%;
    text-align: left;
    border: 1px solid transparent;
    background: none;
    padding: 7px 9px;
    border-radius: var(--radius-sm);
  }
  .hit:hover { border-color: var(--fx-card-border-hover); background: none; }
  .hit:focus-visible { outline: none; box-shadow: var(--focus-ring); }
  .t {
    font-family: var(--font-reading);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin-bottom: 2px;
  }
  .e {
    font-family: var(--font-reading);
    font-size: 12px;
    color: var(--color-text-muted);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .e :global(mark) {
    background: color-mix(in oklab, var(--color-accent) 28%, transparent);
    color: var(--color-text);
    border-radius: 2px;
    padding: 0 1px;
  }
  .tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
  .tag {
    font-size: 10px;
    padding: 0 6px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--color-border);
    color: var(--color-accent);
  }
  .empty,
  .foot {
    margin: 0;
    padding: 9px 11px;
    font-size: 11px;
    color: var(--color-text-muted);
  }
  .foot { border-top: 1px solid var(--color-border); }
  .dim { color: var(--color-text-muted); opacity: 0.75; }
</style>
