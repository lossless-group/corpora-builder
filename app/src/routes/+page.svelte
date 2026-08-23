<script lang="ts">
  import { mode } from '$lib/mode.svelte';
  import DomainCombo from '$lib/components/DomainCombo.svelte';
  import CorpusTree from '$lib/components/CorpusTree.svelte';
  import type { TreeNode, FocusDef } from '$lib/api';
  import { Latest } from '$lib/latest';
  import { SvelteSet } from 'svelte/reactivity';
  import { onMount } from 'svelte';
  import { api, type CaptureResult, type Change, type Meta, type SourceRow } from '$lib/api';

  let meta = $state<Meta | null>(null);
  let rows = $state<SourceRow[]>([]);
  let total = $state(0);
  let search = $state('');
  let domainFilter = $state('');
  let booting = $state(true);
  let bootError = $state('');

  let url = $state('');
  let domain = $state('');
  let full = $state(false);
  let capturing = $state(false);
  let captured = $state<CaptureResult | null>(null);
  let captureError = $state('');

  let tab = $state<'sources' | 'files' | 'changes'>('sources');

  // ── Focus: "mainly look here" ──────────────────────────────────────────
  // Emphasis, not a filter. Everything the client has stays in the list; the
  // focused sources simply come first. A filter would remove exactly the access
  // the `domains:` tag exists to preserve.
  let focus = $state('');
  let focusedTotal = $state(0);

  // Every request takes a number and stale answers are dropped. A search reads
  // the whole corpus (1.2-5.8s) while an unsearched page reads fifty files
  // (0.48s), so clearing the box issues a fast request while a slow one is
  // still in flight — and without this, whichever lands last wins.
  const inflight = new Latest();

  // ── The Files surface ──────────────────────────────────────────────────
  // Fetched once and kept: the tree is derived from keys, so it is one cheap
  // call, and re-fetching it on every tab switch would be motion without gain.
  let tree = $state<TreeNode[] | null>(null);
  let treeTotal = $state(0);
  let treeError = $state('');
  // Open folders, by path. Root children start open; everything deeper is a
  // request — 944 rows at once is the same failure as 112 <option>s.
  let openDirs = $state(new SvelteSet<string>());

  async function loadTree() {
    if (tree) return;
    // Clear the previous failure BEFORE retrying: the template checks
    // `treeError` first, so a retry that succeeded would have gone on showing
    // the old error forever. The failure this fixes is the ordinary one — a
    // sidecar older than the frontend, which is every `tauri dev` session where
    // a Python endpoint was added since the process started.
    treeError = '';
    try {
      const data = await api.tree();
      tree = data.tree;
      treeTotal = data.total;
      // Only `live/` — the corpus's actual content. `bin/` is content-addressed,
      // so its contents are the point and its structure carries nothing; 92 rows
      // of hex digest is not a useful first impression of somebody's corpus.
      openDirs.add('live/');
    } catch (err) {
      treeError = String(err);
    }
  }

  function toggleDir(path: string) {
    openDirs.has(path) ? openDirs.delete(path) : openDirs.add(path);
  }

  /** A folder narrows the Sources list; a file opens in the viewer. */
  async function pickNode(node: TreeNode) {
    if (node.is_dir) {
      // The tree speaks keys (`live/funders/x/`); the filter speaks domains.
      // `_domain_of` strips exactly this, so the client does the mirror of it
      // rather than inventing a second notion of what a domain is.
      domainFilter = node.path
        .replace(/^live\//, '')
        .replace(/\/sources\/$/, '/')
        .replace(/\/$/, '');
      tab = 'sources';
      await load();
      return;
    }
    await view({ path: node.path, title: node.name } as SourceRow);
  }
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
    const data = await inflight.run(() => api.sources(domainFilter, search, focus));
    if (!data) return; // superseded — the operator has moved on
    rows = data.rows;
    total = data.total;
    focusedTotal = data.focused_total;
  }

  function toggleFocus(value: string) {
    focus = focus === value ? '' : value;
    tab = 'sources';
    load();
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
    <button class="mode" onclick={() => mode.cycle()} title="Cycle light / dark / vibrant">{mode.current}</button>
    <input bind:value={search} oninput={debounced} type="search" placeholder="Search title, excerpt, or path…" />
    <div class="dom">
      <DomainCombo
        bind:value={domainFilter}
        domains={meta?.domains ?? []}
        anyLabel="All domains"
        placeholder="All domains — type to filter…"
        onchange={load}
      />
    </div>
  </div>

  {#if (meta?.focuses ?? []).length}
    <!-- "Mainly look here." Prominent by design: this is the first thing you
         reach for when drafting against a strategy, and the labels are the
         corpus's own declared titles rather than slugs. -->
    <div class="focuses">
      {#each meta?.focuses ?? [] as f (f.value)}
        <button
          class="focus"
          class:on={focus === f.value}
          title="{f.type}: {f.folder}"
          aria-pressed={focus === f.value}
          onclick={() => toggleFocus(f.value)}>{f.label}</button
        >
      {/each}
      {#if focus}
        <button class="focus clear" onclick={() => toggleFocus(focus)}>clear</button>
      {/if}
    </div>
  {/if}

  {#if meta?.writable}
    <form class="bar capture" onsubmit={capture}>
      <input bind:value={url} placeholder="Paste a URL to capture…" />
      <div class="dom">
        <DomainCombo
          bind:value={domain}
          domains={meta?.domains ?? []}
          allowNew
          placeholder="file under… (optional)"
        />
      </div>
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
      <button class:on={tab === 'files'} onclick={() => { tab = 'files'; loadTree(); }}>Files</button>
      <button class:on={tab === 'changes'} onclick={() => (tab = 'changes')}>What changed</button>
    </nav>

    {#if tab === 'files'}
      {#if treeError}
        <p class="note err">Could not read the corpus: {treeError}</p>
        <p class="note">
          A <code>404</code> here usually means the backend is older than this
          window — it does not restart when Python changes.
          <button onclick={loadTree}>Retry</button>
        </p>
      {:else if !tree}
        <p class="note">Reading the corpus…</p>
      {:else}
        <p class="count">{treeTotal} objects</p>
        <CorpusTree nodes={tree} open={openDirs} ontoggle={toggleDir} onpick={pickNode} />
      {/if}
    {:else if tab === 'changes'}
      <form class="repo" onsubmit={(e) => { e.preventDefault(); loadChanges(); }}>
        <input
          bind:value={changesRepo}
          placeholder="path to the git repo holding this corpus"
          spellcheck="false"
        />
        <button type="submit" class="go" disabled={loadingChanges || !changesRepo.trim()}>
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

    <!-- Both numbers, always. "34 sources" would read as a filter; the whole
         point of a focus is that the other 811 are still there. -->
    <p class="count">
      {#if focus && focusedTotal}
        <strong>{focusedTotal}</strong> to start with · {total} available{rows.length < total
          ? ` · showing ${rows.length}`
          : ''}
      {:else}
        {total} source{total === 1 ? '' : 's'}{rows.length < total
          ? ` · showing ${rows.length}`
          : ''}
      {/if}
    </p>

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
                <span class="chip" class:on={row.binary_state === 'present'}>
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
  /* The family idiom, from augment-it's member stylesheets: a monospace
     instrument panel where every element carries a 1px border, chips and
     buttons sit on --color-surface-raised, inputs on --color-field, and hover
     is expressed on the BORDER rather than the fill. An earlier pass here
     renamed the tokens to match augment-it and changed nothing visible, which
     is what a rename does. This is the part that shows. */

  header { position: sticky; top: 0; z-index: 5; background: var(--color-surface); border-bottom: 1px solid var(--color-border); padding: 8px 16px; }
  .bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .capture { margin-top: 8px; }
  h1 { font-size: 13px; margin: 0; font-weight: 700; letter-spacing: 0; }
  h1 span { color: var(--color-text-muted); font-weight: 400; }

  /* The control primitive is global, in tokens.css. Everything here states
     only what differs from it. */
  input[type='search'], .capture input:first-of-type { flex: 1; min-width: 200px; }
  .dom { width: 280px; flex: 0 0 auto; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-text-muted); flex: 0 0 auto; white-space: nowrap; }
  .check input { width: auto; min-width: 0; padding: 0; margin: 0; accent-color: var(--color-accent); }
  .ro { margin: 6px 0 0; font-size: 11px; color: var(--color-text-muted); }
  code { font-size: 11px; }

  main { padding: 12px 16px 60px; max-width: 1100px; }
  .count { color: var(--color-text-muted); font-size: 11px; margin: 0 0 10px; }
  .note { color: var(--color-text-muted); padding: 8px 0; }
  .note.ok { color: var(--color-accent); }
  .note.err { color: var(--color-warn-text); }

  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  li { background: var(--color-surface); border: 1px solid var(--fx-card-border); border-radius: var(--radius-md); }
  li.err { border-color: var(--color-warn-text); }
  .card { display: block; width: 100%; text-align: left; background: none; border: 0; padding: 9px 11px; border-radius: var(--radius-md); }
  /* Hover moves the border, not the fill — 845 rows of shifting background is
     noise, and it is how every control in the family signals the same thing. */
  .card:hover { background: none; }
  li:has(.card:hover) { border-color: var(--fx-card-border-hover); }
  .card:focus-visible { outline: none; box-shadow: var(--focus-ring); }

  /* The one reading surface. Title and excerpt keep the sans face because this
     is a list someone scans for meaning; everything around them is instrument. */
  .t { font-family: var(--font-reading); font-size: 14px; font-weight: 600; letter-spacing: -.01em; margin-bottom: 2px; }
  .e { font-family: var(--font-reading); font-size: 13px; color: var(--color-text-muted); }
  li.err .t { color: var(--color-warn-text); }
  .x { color: var(--color-text-muted); font-size: 11px; margin-bottom: 4px; word-break: break-all; }

  /* Chips, not tabs: several may be on-topic at once and none of them is a
     mode. Sized up from the 11px metadata scale because this is a control the
     operator reaches for first, not a label they read in passing. */
  .focuses { display: flex; gap: 6px; flex-wrap: wrap; padding: 8px 16px; border-bottom: 1px solid var(--color-border); }
  .focus { font-size: 12px; border-radius: var(--radius-pill); color: var(--color-text-muted); }
  .focus.on { background: var(--color-accent); color: var(--color-on-accent); border-color: var(--color-accent); }
  .focus.clear { color: var(--color-warn-text); }

  .tabs { display: flex; gap: 6px; margin: 0 0 var(--space-md); }
  .tabs button { border-radius: var(--radius-pill); color: var(--color-text-muted); font-size: 12px; }
  .tabs button.on { background: var(--color-accent); color: var(--color-on-accent); border-color: var(--color-accent); }

  .repo { display: flex; gap: 8px; margin-bottom: var(--space-sm); }
  .repo input { flex: 1; min-width: 200px; }
  .repo button.go { background: var(--color-accent); color: var(--color-on-accent); border-color: var(--color-accent); }

  /* A feed entry is a card that is not clickable — same padding and radius, no
     hover, because there is nothing to open. */
  .feed { list-style: none; padding: 0; margin: 0; }
  .feed li { padding: 9px 11px; border-radius: var(--radius-md); }
  .feed li + li { border-top: 1px solid var(--color-border); border-radius: 0; }
  .feed .when { color: var(--color-text-muted); font-size: 11px; }
  .feed .why { font-family: var(--font-reading); font-size: 13px; font-weight: 600; margin: 2px 0 4px; }
  .feed .counts { display: flex; gap: 10px; color: var(--color-text-muted); font-size: 11px; }

  .getpdf { display: inline-block; margin: 0 0 7px 11px; font-size: 11px; color: var(--color-accent); text-decoration: none; }
  .getpdf:hover { text-decoration: underline; }

  /* A chip is bordered and sits on the raised surface, so a row of them reads
     as a row of keys rather than a row of highlights. */
  .chips { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 7px; }
  .chip { font-size: 11px; padding: 1px 7px; border-radius: var(--radius-pill); border: 1px solid var(--color-border); background: var(--color-surface-raised); color: var(--color-text-muted); }
  .chip.on { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-on-accent); }

  .mode { text-transform: uppercase; letter-spacing: .04em; font-size: 11px; color: var(--color-text-muted); min-width: 68px; }
  .backdrop { position: fixed; inset: 0; background: var(--fx-scrim); display: grid; place-items: center; padding: 24px; }
  .modal { background: var(--color-surface); border: 1px solid var(--color-border-strong); border-radius: var(--radius-lg); max-width: min(880px, 94vw); width: 100%; }
  .mhead { border-bottom: 1px solid var(--color-border); padding: 9px 13px; }
  .mhead h1 { flex: 1; }
  pre { margin: 0; padding: 13px 15px; overflow: auto; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 66vh; }
</style>
