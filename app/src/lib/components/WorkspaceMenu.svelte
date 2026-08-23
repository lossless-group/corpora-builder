<script lang="ts">
  /**
   * Which corpus am I in — `context-v/specs/Header-Chrome.md`.
   *
   * Ported from `augment-it/shell/src/WorkspaceSwitcher.svelte`: same trigger
   * (dot, label, chevron), same listbox, same interaction contract. Pattern
   * port, NOT a shared dependency, per the no-shared-dependency-across-ai-labs-
   * apps convention — and top-right for the same reason, so someone who uses
   * both apps does not have to look in two places.
   *
   * The trigger carries the display name ONLY. The slug lives on the row inside
   * the dropdown, which is where an operator goes when they need to know exactly
   * which corpus they are pointed at. The header used to read
   * `reach-edu (reach-edu)` — a slug printed twice, with a bucket name leaking
   * into the product.
   *
   * One workspace today. The listbox shape is here because switching is the
   * whole point of the control, and a one-row list that becomes a two-row list
   * is not a rewrite.
   */
  import type { WorkspaceInfo } from '$lib/api';
  import { workspaceLabel, workspaceStorage } from '$lib/workspace';

  interface Props {
    workspace: WorkspaceInfo | null;
    /** The server's own name for the corpus. Predates `workspace` and is the
     *  fallback when a client is holding a payload older than that field. */
    label?: string;
    writable?: boolean;
  }
  let { workspace, label: metaLabel = '', writable = false }: Props = $props();

  let open = $state(false);
  let el = $state<HTMLDivElement | undefined>(undefined);

  /**
   * Degrade to the name we have always had, never to nothing.
   *
   * Reported from the running app as a blank trigger: Vite HMR swapped this
   * component in without re-running the initial fetch, so `meta` was the object
   * returned by a sidecar that predated the `workspace` field. A hard reload
   * fixes that instance; showing an em dash where `label` was sitting unused is
   * the part that was actually wrong.
   */
  const label = $derived(workspaceLabel(workspace, metaLabel));
  /** Only claim to know where the bytes live when we were actually told. */
  const storage = $derived(workspaceStorage(workspace));

  function onDocPointer(ev: PointerEvent) {
    if (open && el && !el.contains(ev.target as Node)) open = false;
  }
  function onKey(ev: KeyboardEvent) {
    if (ev.key === 'Escape' && open) open = false;
  }

  $effect(() => {
    document.addEventListener('pointerdown', onDocPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDocPointer);
      document.removeEventListener('keydown', onKey);
    };
  });
</script>

<div class="ws" bind:this={el}>
  <button
    type="button"
    class="trigger"
    class:open
    aria-haspopup="listbox"
    aria-expanded={open}
    title="Corpus: {workspace?.slug ?? 'unknown'}"
    onclick={() => (open = !open)}
  >
    <span class="dot" aria-hidden="true"></span>
    <span class="label">{label}</span>
    <span class="chev" aria-hidden="true">{open ? '▴' : '▾'}</span>
  </button>

  {#if open}
    <ul class="menu" role="listbox" aria-label="Corpora">
      <li>
        <button type="button" class="row active" role="option" aria-selected="true">
          <span class="row-label">{label}</span>
          <!-- The slug, visible only here — and omitted rather than blank when
               the payload did not carry one. -->
          {#if workspace?.slug}<span class="row-slug">{workspace.slug}</span>{/if}
          <span class="check" aria-hidden="true">✓</span>
        </button>
      </li>
      <li class="foot">
        {storage ? `${storage} · ` : ''}{writable ? 'writable' : 'read-only'}
      </li>
    </ul>
  {/if}
</div>

<style>
  .ws { position: relative; display: inline-flex; align-items: center; }

  .trigger { display: inline-flex; align-items: center; gap: .4rem; background: transparent; padding: 3px 9px; font-size: 12px; }
  .trigger:hover, .trigger.open { border-color: var(--color-accent); color: var(--color-accent); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--color-accent); flex-shrink: 0; }
  .label { font-weight: 600; letter-spacing: .02em; }
  .chev { color: var(--color-text-muted); }

  .menu {
    position: absolute; top: calc(100% + 4px); right: 0; z-index: 30;
    margin: 0; padding: 3px; list-style: none; min-width: 220px;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    box-shadow: var(--fx-card-shadow);
  }
  .row {
    display: flex; align-items: baseline; gap: 8px; width: 100%; text-align: left;
    background: none; border: 1px solid transparent; border-radius: var(--radius-sm);
    padding: 4px 8px; color: var(--color-text); font-size: 12px;
  }
  .row:hover { border-color: var(--fx-card-border-hover); }
  .row-slug { color: var(--color-text-muted); font-size: 11px; }
  .check { margin-left: auto; color: var(--color-accent); }
  .foot { padding: 4px 8px 3px; font-size: 11px; color: var(--color-text-muted); border-top: 1px solid var(--color-border); margin-top: 3px; }
</style>
