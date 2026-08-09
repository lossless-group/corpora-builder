<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type CaptureResult, type Meta, type SourceRow } from '$lib/api';

  let meta = $state<Meta | null>(null);
  let rows = $state<SourceRow[]>([]);
  let total = $state(0);
  let search = $state('');
  let prefix = $state('');
  let booting = $state(true);
  let bootError = $state('');

  let url = $state('');
  let domain = $state('');
  let full = $state(false);
  let capturing = $state(false);
  let captured = $state<CaptureResult | null>(null);
  let captureError = $state('');

  let viewing = $state<SourceRow | null>(null);
  let viewingText = $state('');

  let timer: ReturnType<typeof setTimeout>;

  onMount(async () => {
    // The Rust side spawns the sidecar at launch, but the webview can be ready
    // first. Poll rather than showing an error the operator would have to
    // resolve by restarting.
    for (let attempt = 0; attempt < 40; attempt++) {
      try {
        meta = await api.meta();
        booting = false;
        await load();
        return;
      } catch {
        await new Promise((r) => setTimeout(r, 400));
      }
    }
    booting = false;
    bootError = 'The backend did not start. Check that `uv sync --extra dev` has been run.';
  });

  async function load() {
    const data = await api.sources(prefix, search);
    rows = data.rows;
    total = data.total;
  }

  function debounced() {
    clearTimeout(timer);
    timer = setTimeout(load, 160);
  }

  async function capture(event: Event) {
    event.preventDefault();
    if (!url.trim() || capturing) return;
    capturing = true;
    captureError = '';
    captured = null;
    try {
      captured = await api.capture(url.trim(), domain.trim(), full);
      url = '';
      await load();
      meta = await api.meta();
    } catch (err) {
      captureError = err instanceof Error ? err.message : String(err);
    } finally {
      capturing = false;
    }
  }

  async function view(row: SourceRow) {
    viewing = row;
    viewingText = 'Loading…';
    try {
      viewingText = await api.source(row.path);
    } catch (err) {
      viewingText = `Could not load: ${err}`;
    }
  }

  function chips(row: SourceRow): [string, boolean][] {
    if (row.error) return [['error', true], [row.domain, false]];
    return [
      [row.status, row.status === 'promoted'],
      [row.content_pulled ? 'body: yes' : 'body: no', false],
      ...(row.published_at ? ([[`pub ${row.published_at}`, false]] as [string, boolean][]) : []),
      [row.domain, false]
    ];
  }
</script>

<header>
  <div class="bar">
    <h1>corpora <span>{meta?.label ?? ''}</span></h1>
    <input bind:value={search} oninput={debounced} type="search" placeholder="Search title, excerpt, or path…" />
    <select bind:value={prefix} onchange={load}>
      <option value="">All domains</option>
      {#each meta?.domains ?? [] as d}
        <option value={d.startsWith('(') ? '' : `${d}/`}>{d}</option>
      {/each}
    </select>
  </div>

  {#if meta?.writable}
    <form class="bar capture" onsubmit={capture}>
      <input bind:value={url} placeholder="Paste a URL to capture…" />
      <input bind:value={domain} class="dom" placeholder="domain (optional)" />
      <label class="check"><input type="checkbox" bind:checked={full} /> fetch body</label>
      <button disabled={capturing || !url.trim()}>{capturing ? 'Fetching…' : 'Capture'}</button>
    </form>
  {:else if meta}
    <p class="ro">Read-only. Restart with <code>--writable</code> to capture.</p>
  {/if}
</header>

<main>
  {#if booting}
    <p class="note">Starting the backend…</p>
  {:else if bootError}
    <p class="note err">{bootError}</p>
  {:else}
    {#if captured}
      <p class="note ok">
        {#if captured.created}
          Added <strong>{captured.title || captured.path}</strong> — {captured.machine_verdict}
        {:else}
          Already in the corpus → <code>{captured.duplicate_of}</code>
        {/if}
      </p>
    {/if}
    {#if captureError}<p class="note err">{captureError}</p>{/if}

    <p class="count">{total} source{total === 1 ? '' : 's'}{rows.length < total ? ` · showing ${rows.length}` : ''}</p>

    <ul>
      {#each rows as row (row.path)}
        <li class:err={row.error}>
          <button class="card" onclick={() => view(row)}>
            <div class="t">{row.title || '(untitled)'}</div>
            <div class="x">{row.error || row.url || row.path}</div>
            {#if row.excerpt}<div class="e">{row.excerpt}</div>{/if}
            <div class="chips">
              {#each chips(row) as [text, on]}<span class="chip" class:on>{text}</span>{/each}
            </div>
          </button>
        </li>
      {:else}
        <li class="note">Nothing matches.</li>
      {/each}
    </ul>
  {/if}
</main>

{#if viewing}
  <div
    class="backdrop"
    role="button"
    tabindex="0"
    onclick={() => (viewing = null)}
    onkeydown={(e) => e.key === 'Escape' && (viewing = null)}
  >
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
    <div class="modal" role="document" onclick={(e) => e.stopPropagation()}>
      <div class="bar mhead">
        <h1>{viewing.title || viewing.path}</h1>
        <button onclick={() => (viewing = null)}>Close</button>
      </div>
      <pre>{viewingText}</pre>
    </div>
  </div>
{/if}

<style>
  header { position: sticky; top: 0; z-index: 5; background: var(--bg); border-bottom: 1px solid var(--line); padding: 12px 18px; }
  .bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .capture { margin-top: 10px; }
  h1 { font-size: 14.5px; margin: 0; font-weight: 620; letter-spacing: -.01em; }
  h1 span { color: var(--dim); font-weight: 420; font-size: 13px; }
  input, select, button { font: inherit; padding: 7px 10px; border-radius: 7px; border: 1px solid var(--line); background: var(--panel); color: var(--ink); }
  input[type='search'], .capture input:first-of-type { flex: 1; min-width: 200px; }
  .dom { width: 190px; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--dim); flex: 0 0 auto; white-space: nowrap; }
  .check input { width: auto; min-width: 0; padding: 0; margin: 0; accent-color: var(--accent); }
  button { cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  .ro { margin: 8px 0 0; font-size: 12.5px; color: var(--dim); }
  code { font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
  main { padding: 16px 18px 60px; max-width: 1100px; }
  .count { color: var(--dim); font-size: 13px; margin: 0 0 12px; }
  .note { color: var(--dim); padding: 10px 0; }
  .note.ok { color: var(--accent); }
  .note.err { color: var(--warn); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 9px; }
  li { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--shadow); }
  li.err { border-color: var(--warn); }
  .card { display: block; width: 100%; text-align: left; background: none; border: 0; padding: 12px 14px; border-radius: 10px; }
  .card:hover { background: var(--chip); }
  .t { font-weight: 580; margin-bottom: 3px; }
  li.err .t { color: var(--warn); }
  .x { color: var(--dim); font-size: 12.5px; margin-bottom: 5px; word-break: break-all; }
  .e { color: var(--dim); font-size: 13.5px; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .chip { font-size: 11.5px; padding: 2px 8px; border-radius: 100px; background: var(--chip); color: var(--dim); }
  .chip.on { background: var(--accent); color: var(--bg); }
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 24px; }
  .modal { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; max-width: min(880px, 94vw); width: 100%; }
  .mhead { border-bottom: 1px solid var(--line); padding: 12px 16px; }
  .mhead h1 { flex: 1; }
  pre { margin: 0; padding: 16px 18px; overflow: auto; font-size: 12.5px; font-family: ui-monospace, Menlo, monospace; white-space: pre-wrap; word-break: break-word; max-height: 66vh; }
</style>
