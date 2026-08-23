<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type CaptureResult, type Change, type Meta, type SourceRow } from '$lib/api';

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

  let tab = $state<'sources' | 'changes'>('sources');
  let changes = $state<Change[]>([]);
  let changesTruncated = $state(false);
  let changesRepo = $state('');
  let changesError = $state('');
  let loadingChanges = $state(false);

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

  async function loadChanges() {
    if (!changesRepo.trim()) return;
    loadingChanges = true;
    changesError = '';
    try {
      const page = await api.changes(changesRepo.trim(), 'corpus', 25);
      changes = page.changes;
      changesTruncated = page.truncated;
    } catch (e) {
      changesError = String(e instanceof Error ? e.message : e);
      changes = [];
    } finally {
      loadingChanges = false;
    }
  }

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

  function kb(n: number): string {
    if (!n) return '';
    return n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
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

    <nav class="tabs">
      <button class:on={tab === 'sources'} onclick={() => (tab = 'sources')}>Sources</button>
      <button class:on={tab === 'changes'} onclick={() => (tab = 'changes')}>What changed</button>
    </nav>

    {#if tab === 'changes'}
      <form class="repo" onsubmit={(e) => { e.preventDefault(); loadChanges(); }}>
        <input
          bind:value={changesRepo}
          placeholder="path to the git repo holding this corpus"
          spellcheck="false"
        />
        <button type="submit" disabled={loadingChanges || !changesRepo.trim()}>
          {loadingChanges ? 'Reading…' : 'Show'}
        </button>
      </form>
      <p class="note">
        History lives in git today. When it moves — a Kopia repository, our own
        checkpoints — this field is what changes, not what you see below.
      </p>
      {#if changesError}<p class="note err">{changesError}</p>{/if}

      <ul class="feed">
        {#each changes as c (c.id)}
          <li>
            <div class="when">{c.when.slice(0, 10)} · {c.who}</div>
            <!-- No sentence means no reason line. Never a generated one: an
                 absent reason renders as absent, which is honest and is the only
                 thing that creates pressure to write a real one. -->
            {#if c.sentence && c.sentence.trim()}
              <div class="why">{c.sentence}</div>
            {/if}
            <div class="counts">
              {#if c.counts.added}<span>{c.counts.added} added</span>{/if}
              {#if c.counts.changed}<span>{c.counts.changed} updated</span>{/if}
              {#if c.counts.removed}<span>{c.counts.removed} removed</span>{/if}
              {#if c.counts.renamed}<span>{c.counts.renamed} moved</span>{/if}
              {#if c.bytes}<span class="dim">{kb(c.bytes)}</span>{/if}
            </div>
          </li>
        {:else}
          {#if !loadingChanges && changesRepo}<li class="note">No changes found.</li>{/if}
        {/each}
      </ul>
      {#if changesTruncated}
        <p class="note">Showing the {changes.length} most recent; there are more.</p>
      {/if}
    {:else}

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
              {#if row.binary_key}
                <span class="chip pdf" class:dim={row.binary_state === 'not_downloaded'}>
                  PDF {kb(row.binary_bytes)}{row.binary_optimized ? ' · optimized' : ''}
                </span>
              {/if}
            </div>
          </button>
          {#if row.binary_key}
            <!-- A plain link, deliberately. The binary is bytes the browser can
                 open; routing it through JS would add a copy and lose the
                 viewer the reader already has. -->
            <a
              class="getpdf"
              href={api.binaryUrl(row.binary_key)}
              target="_blank"
              rel="noreferrer"
              title={row.binary_key}
            >{row.binary_state === 'present' ? 'Open PDF' : 'Download PDF'}</a>
          {/if}
        </li>
      {:else}
        <li class="note">Nothing matches.</li>
      {/each}
    </ul>
    {/if}
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
  h1 span { color: var(--ink-dim); font-weight: 420; font-size: 13px; }
  input, select, button { font: inherit; padding: 7px 10px; border-radius: var(--radius-sm); border: 1px solid var(--line); background: var(--surface); color: var(--ink); }
  input[type='search'], .capture input:first-of-type { flex: 1; min-width: 200px; }
  .dom { width: 190px; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-dim); flex: 0 0 auto; white-space: nowrap; }
  .check input { width: auto; min-width: 0; padding: 0; margin: 0; accent-color: var(--accent); }
  button { cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
  .ro { margin: 8px 0 0; font-size: 12.5px; color: var(--ink-dim); }
  code { font-family: var(--font-mono); font-size: 12px; }
  main { padding: 16px 18px 60px; max-width: 1100px; }
  .count { color: var(--ink-dim); font-size: 13px; margin: 0 0 12px; }
  .note { color: var(--ink-dim); padding: 10px 0; }
  .note.ok { color: var(--accent); }
  .note.err { color: var(--warn); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 9px; }
  li { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-md); box-shadow: var(--shadow); }
  li.err { border-color: var(--warn); }
  .card { display: block; width: 100%; text-align: left; background: none; border: 0; padding: 12px 14px; border-radius: var(--radius-md); }
  .card:hover { background: var(--surface-hover); }
  .t { font-weight: 580; margin-bottom: 3px; }
  li.err .t { color: var(--warn); }
  .x { color: var(--ink-dim); font-size: 12.5px; margin-bottom: 5px; word-break: break-all; }
  .e { color: var(--ink-dim); font-size: 13.5px; }
  .tabs { display: flex; gap: 4px; margin: 0 0 var(--space-md); }
  .tabs button {
    font: inherit; font-size: 13px; padding: 6px 14px; cursor: pointer;
    border: 1px solid var(--line); background: var(--surface); color: var(--ink-dim);
    border-radius: var(--radius-pill);
  }
  .tabs button.on { background: var(--accent); color: var(--accent-ink); border-color: transparent; }

  .repo { display: flex; gap: 8px; margin-bottom: var(--space-sm); }
  .repo input {
    flex: 1; font: inherit; font-size: 13px; font-family: var(--font-mono);
    padding: 7px 10px; border: 1px solid var(--line); border-radius: var(--radius-md);
    background: var(--surface); color: var(--ink);
  }
  .repo button {
    font: inherit; font-size: 13px; padding: 7px 14px; cursor: pointer;
    border: 0; border-radius: var(--radius-md); background: var(--accent); color: var(--accent-ink);
  }
  .repo button:disabled { opacity: .5; cursor: default; }

  .feed { list-style: none; padding: 0; margin: var(--space-md) 0 0; }
  .feed li { padding: 12px 0; border-bottom: 1px solid var(--line); }
  .feed .when { font-size: 12px; color: var(--ink-dim); font-family: var(--font-mono); }
  .feed .why { margin: 4px 0 6px; font-size: 14.5px; color: var(--ink); }
  .feed .counts { display: flex; gap: 10px; font-size: 12px; color: var(--ink-dim); }
  .feed .counts .dim { opacity: .7; }

  .getpdf {
    display: inline-block; margin: 2px 0 10px; font-size: 12px;
    color: var(--accent); text-decoration: none;
  }
  .getpdf:hover { text-decoration: underline; }
  .chip.pdf { background: var(--accent); color: var(--accent-ink); }
  .chip.pdf.dim { background: var(--chip-bg); color: var(--ink-dim); }

  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .chip { font-size: 11.5px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--chip-bg); color: var(--ink-dim); }
  .chip.on { background: var(--accent); color: var(--accent-ink); }
  .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: grid; place-items: center; padding: 24px; }
  .modal { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius-lg); max-width: min(880px, 94vw); width: 100%; }
  .mhead { border-bottom: 1px solid var(--line); padding: 12px 16px; }
  .mhead h1 { flex: 1; }
  pre { margin: 0; padding: 16px 18px; overflow: auto; font-size: 12.5px; font-family: var(--font-mono); white-space: pre-wrap; word-break: break-word; max-height: 66vh; }
</style>
