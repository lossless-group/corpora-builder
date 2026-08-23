<script lang="ts">
  /**
   * A combobox over the corpus's domain folders — `context-v/specs/Domain-Navigation.md`.
   *
   * Replaces a `<select>` that reach-edu filled with 112 options, 66 of them
   * under `funders/`. All the matching rules live in `$lib/domains` and are
   * tested there; this file is the shell — focus, keys, and the listbox.
   *
   * Two behaviours are worth reading the code for:
   *
   * 1. **Backspace deletes a path segment**, but only when the current value
   *    names a real domain or a real prefix. `isNavigable()` asks the corpus,
   *    so there is no mode flag to fall out of sync with what the operator sees.
   *    Mid-typing, Backspace is an ordinary Backspace.
   *
   * 2. **The shared prefix is dimmed**, not hidden. `funders/` printed 66 times
   *    at full contrast is what made the list unreadable; removing it entirely
   *    would lose the fact that these rows are paths.
   */
  import { chopSegment, isNavigable, rank, splitForDisplay } from '$lib/domains';

  interface Props {
    value: string;
    domains: string[];
    /** Capture files somewhere new; the filter only picks what exists. */
    allowNew?: boolean;
    placeholder?: string;
    /** Label for the "no filter" row. Omit to leave the empty value unofferable. */
    anyLabel?: string;
    onchange?: (value: string) => void;
  }

  let {
    value = $bindable(),
    domains,
    allowNew = false,
    placeholder = 'domain…',
    anyLabel,
    onchange,
  }: Props = $props();

  let open = $state(false);
  let active = $state(0);
  let el: HTMLInputElement;

  // The query is the field itself: this is a combobox, not a search box with a
  // separate result set, so what you see is always what is being matched.
  let hits = $derived(rank(value, domains));
  let navigable = $derived(isNavigable(value, domains));
  let unknown = $derived(value !== '' && !domains.includes(value));

  function commit(v: string) {
    value = v;
    open = false;
    active = 0;
    onchange?.(v);
  }

  function onInput() {
    open = true;
    active = 0;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      open = true;
      const n = hits.length;
      if (n) active = (active + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (open && hits[active]) commit(hits[active]);
      else commit(value);
      return;
    }
    if (e.key === 'Tab' && open && hits[active]) {
      // Complete rather than leave: Tab out of a half-typed domain is almost
      // always a completion the operator meant to accept.
      e.preventDefault();
      commit(hits[active]);
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      if (open) open = false;
      else commit('');
      return;
    }
    if (e.key === 'Backspace') {
      const atEnd = el.selectionStart === value.length && el.selectionEnd === value.length;
      if (atEnd && navigable) {
        e.preventDefault();
        commit(chopSegment(value));
        open = true;
      }
    }
  }
</script>

<div class="combo">
  <input
    bind:this={el}
    bind:value
    {placeholder}
    role="combobox"
    aria-expanded={open}
    aria-controls="domain-listbox"
    aria-autocomplete="list"
    aria-activedescendant={open && hits[active] ? `domain-opt-${active}` : undefined}
    autocomplete="off"
    spellcheck="false"
    class:unknown={unknown && !allowNew}
    oninput={onInput}
    onkeydown={onKey}
    onfocus={() => (open = true)}
    onblur={() => setTimeout(() => (open = false), 120)}
  />

  {#if open}
    <ul class="list" id="domain-listbox" role="listbox">
      {#if anyLabel && value !== ''}
        <li>
          <button type="button" class="opt any" onmousedown={() => commit('')}>{anyLabel}</button>
        </li>
      {/if}
      {#each hits as d, i (d)}
        {@const parts = splitForDisplay(d)}
        <li>
          <button
            type="button"
            id="domain-opt-{i}"
            role="option"
            aria-selected={i === active}
            class="opt"
            class:on={i === active}
            onmousedown={() => commit(d)}
          >
            {#if parts.prefix}<span class="pre">{parts.prefix}</span>{/if}{parts.rest}
          </button>
        </li>
      {/each}
      {#if hits.length === 0}
        <li class="empty">
          {#if allowNew && value}
            <button type="button" class="opt new" onmousedown={() => commit(value)}>
              file under <span class="pre">new</span> {value}
            </button>
          {:else}
            no domain matches “{value}”
          {/if}
        </li>
      {/if}
    </ul>
  {/if}
</div>

<style>
  /* The input inherits the global control rule; only layout differs here. */
  .combo { position: relative; display: flex; }
  .combo input { width: 100%; }
  /* A value that names no real domain, where only real ones are accepted. */
  .combo input.unknown { border-color: var(--color-warn-text); }

  .list {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 20;
    margin: 0;
    padding: 3px;
    list-style: none;
    max-height: 320px;
    overflow-y: auto;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    box-shadow: var(--fx-card-shadow);
  }

  .opt {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 3px 7px;
    color: var(--color-text);
    cursor: pointer;
  }
  .opt:hover,
  .opt.on { background: var(--color-surface-raised); border-color: var(--fx-card-border-hover); }

  /* Dimmed, not removed: the rows are still paths, they just stop shouting the
     part that all 66 of them share. */
  .pre { color: var(--color-text-muted); }

  .any { color: var(--color-text-muted); }
  .new .pre { color: var(--color-accent); }
  .empty { padding: 4px 7px; color: var(--color-text-muted); }
</style>
