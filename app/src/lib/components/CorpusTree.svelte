<script lang="ts">
  /**
   * The corpus as a folder tree — `context-v/specs/Corpus-Tree.md`.
   *
   * Recursive-self-import, the shape borrowed from `flave-ai`'s
   * `apps/editor/src/FileTree.svelte`. Two deliberate departures, both because
   * a corpus is not an editor workspace:
   *
   * 1. **Folders collapse.** flave-ai's directories are always open, which is
   *    right for a workspace of a dozen files and wrong for 944 objects across
   *    five levels. Open state lives here, per node, keyed by path.
   *
   * 2. **Folders are buttons.** In flave-ai a directory is inert — there is
   *    nowhere for it to go. Here a folder maps to a domain, so clicking one
   *    sets the filter. The tree and the combobox are two views of one idea.
   *
   * Indentation is a CSS custom property rather than nested padding, so a deep
   * row still starts from the same left edge computation and the tree does not
   * accumulate margin per level.
   */
  import Self from './CorpusTree.svelte';

  export interface TreeNode {
    name: string;
    path: string;
    is_dir: boolean;
    count: number;
    children: TreeNode[];
  }

  interface Props {
    nodes: TreeNode[];
    depth?: number;
    open: Set<string>;
    ontoggle: (path: string) => void;
    onpick: (node: TreeNode) => void;
  }

  let { nodes, depth = 0, open, ontoggle, onpick }: Props = $props();

  /**
   * Only folders that actually map to a domain get a filter action —
   * `live/<type>/<slug>/`. On `bin/` or on a `sources/` leaf it would mean
   * nothing, and an affordance offered where it does nothing is worse than one
   * that is absent.
   */
  const filterable = (path: string) =>
    /^live\/[^/]+\/[^/]+\/$/.test(path) || /^live\/[^/]+\/$/.test(path);
</script>

<ul class="tree" style="--depth: {depth}">
  {#each nodes as node (node.path)}
    <li>
      {#if node.is_dir}
        <div class="rowwrap">
          <button
            type="button"
            class="row dir"
            aria-expanded={open.has(node.path)}
            onclick={() => ontoggle(node.path)}
          >
            <span class="glyph">{open.has(node.path) ? '▾' : '▸'}</span>{node.name}
            <span class="count">{node.count}</span>
          </button>
          {#if filterable(node.path)}
            <button
              type="button"
              class="filter"
              title="Filter sources to {node.path}"
              onclick={() => onpick(node)}>filter</button
            >
          {/if}
        </div>
        {#if open.has(node.path)}
          <Self nodes={node.children} depth={depth + 1} {open} {ontoggle} {onpick} />
        {/if}
      {:else}
        <button type="button" class="row file" onclick={() => onpick(node)}>
          <span class="glyph">·</span>{node.name}
        </button>
      {/if}
    </li>
  {/each}
</ul>

<style>
  .tree { list-style: none; margin: 0; padding: 0; }

  .rowwrap { display: flex; align-items: stretch; gap: 4px; }
  .rowwrap .row { flex: 1; min-width: 0; }

  /* Rows are not controls: the global `button` rule would give each of 944 a
     border, a field background and 0.35rem of padding, which is a wall. They
     opt out and state their own shape. */
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    text-align: left;
    background: none;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 2px 7px 2px calc(7px + var(--depth) * 13px);
    color: var(--color-text-muted);
    font-size: 12px;
  }
  .row:hover { border-color: var(--fx-card-border-hover); color: var(--color-text); }

  .dir { color: var(--color-text); }
  .file { color: var(--color-text-muted); }

  .glyph { color: var(--color-text-muted); width: 9px; flex: 0 0 auto; }

  /* The number of files beneath, at any depth — the figure that makes a tree
     navigable rather than one you expand hoping. */
  .count {
    margin-left: auto;
    padding-left: 8px;
    font-size: 11px;
    color: var(--color-text-muted);
  }

  .filter {
    flex: 0 0 auto;
    font-size: 11px;
    padding: 0 7px;
    color: var(--color-text-muted);
    background: var(--color-surface-raised);
  }
</style>
