<script lang="ts">
  import { mode } from '$lib/mode.svelte';
  import DomainCombo from '$lib/components/DomainCombo.svelte';
  import CorpusTree from '$lib/components/CorpusTree.svelte';
  import WorkspaceMenu from '$lib/components/WorkspaceMenu.svelte';
  import ModeToggle from '$lib/components/ModeToggle.svelte';
  import CorporaMark from '$lib/components/CorporaMark.svelte';
  import SearchPanel from '$lib/components/SearchPanel.svelte';
  import type { TreeNode, FocusDef } from '$lib/api';
  import { Latest } from '$lib/latest';
  import { SvelteSet } from 'svelte/reactivity';
  import { onMount } from 'svelte';
  import { api, type CaptureResult, type Change, type Meta, type SourceRow } from '$lib/api';
  import {
    RankedSearch,
    decideSearch,
    loadBundle,
    poolCoversCorpus,
    type Bundle
  } from '$lib/search';

  // key → the passage that matched, with <mark> around the terms. Kept beside
  // the rows rather than on them: it belongs to a QUERY, not to a source, and
  // putting it on the row would leave the last search's highlighting behind.
  let marks = $state(new Map<string, string>());

  // The results panel under the box. `context-vigilance-kit/splash` puts search
  // results there rather than only filtering a list further down, and the
  // difference is which question you are asking: the list is "show me
  // everything matching, so I can work through it"; the panel is "did the thing
  // I am thinking of come back", answered without leaving the input.
  let panelOpen = $state(false);
  let searchBox = $state<HTMLDivElement | undefined>(undefined);

  // True from the keystroke until THIS query's rows land. Without it the panel
  // opens on the rows it happens to be holding — which, on an unindexed corpus
  // where a search reads every file, is the unfiltered list for several
  // seconds. Screenshotted mid-flight it is indistinguishable from a working
  // search returning wrong answers, which is the worst thing a search can do.
  let searching = $state(false);

  function closePanel() {
    panelOpen = false;
  }

  function onDocPointer(ev: PointerEvent) {
    if (panelOpen && searchBox && !searchBox.contains(ev.target as Node)) panelOpen = false;
  }

  $effect(() => {
    document.addEventListener('pointerdown', onDocPointer);
    return () => document.removeEventListener('pointerdown', onDocPointer);
  });

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
  let corpusTotal = $state(0);

  // Every request takes a number and stale answers are dropped. Before the
  // manifest a search read the whole corpus (1.2-5.8s) while an unsearched page
  // read fifty files (0.48s), so clearing the box issued a fast request while a
  // slow one was still in flight and whichever landed last won. The manifest
  // makes both one read, which shrinks the window rather than closing it —
  // network ordering is not a promise you get to stop making.
  const inflight = new Latest();

  // ── Ranked search ──────────────────────────────────────────────────────
  // Pagefind ranks, stems, and takes two words in any order. It also cannot
  // stay fresh — it has no incremental add — so it is used only when its
  // recorded fingerprint matches the manifest that is actually there, and the
  // server's manifest-backed search answers whenever it does not. Serving stale
  // ranking silently is worse than serving honest substring matching.
  let bundle = $state<Bundle | null>(null);
  let ranked = $state<RankedSearch | null>(null);
  let searchNote = $state('');
  let indexStale = $state(false);
  let reindexing = $state(false);

  // Rows for the current domain and focus, unsearched. With a manifest this is
  // one read server-side, so it is fetched once per filter change and searched
  // in the browser — which is what makes ranked search instant rather than a
  // round trip per keystroke.
  let pool = $state<SourceRow[]>([]);
  const POOL_LIMIT = 2000;
  const PAGE = 200;

  // Ranked rows are drawn in a much smaller page than unranked ones, and the
  // reason is asymmetric cost: an unsearched page costs nothing per row — the
  // rows are already here — while every ranked row drawn costs one fragment
  // fetch for the passage that matched. Drawing 200 of those was 200 requests
  // per keystroke's worth of search, which is what made it feel slow.
  const RANKED_PAGE = 30;
  let shown = $state(RANKED_PAGE);

  async function wireSearch() {
    const decision = decideSearch(bundle, meta?.search_index ?? '');
    if (decision.mode === 'ranked' && bundle) {
      ranked = new RankedSearch(bundle.api);
      searchNote = '';
    } else {
      ranked = null;
      searchNote = decision.reason;
    }
  }

  async function reindex() {
    if (reindexing) return;
    reindexing = true;
    try {
      await api.reindex();
      meta = await api.meta();
      bundle = await loadBundle(api.pagefindBase(), meta.search_index);
      await wireSearch();
      await load();
    } catch (err) {
      searchNote = err instanceof Error ? err.message : String(err);
    } finally {
      reindexing = false;
    }
  }

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
        // Loading the bundle is a fetch of a WebAssembly module; a corpus with
        // no search index simply gets `null` back and the server does the
        // searching, so this never blocks the first paint.
        bundle = await loadBundle(api.pagefindBase(), meta.search_index);
        await wireSearch();
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
    if (ranked) {
      const data = await inflight.run(() => api.sources(domainFilter, '', focus, POOL_LIMIT));
      if (!data) return; // superseded — a newer request owns `searching` now
      pool = data.rows;
      corpusTotal = data.corpus_total;
      indexStale = data.index_stale;
      // Against `data.total`, NOT the corpus: the pool only ever has to cover
      // what the current domain and focus select. Comparing to the corpus made
      // every focus chip stand ranking down — 41 rows held, 847 in the corpus,
      // and the two were never going to match. Found by driving it.
      if (!poolCoversCorpus(pool.length, data.total)) {
        // Genuinely more rows than we hold. A ranked hit outside the window has
        // no row to render and would simply disappear — so stand down and say
        // why, rather than quietly answering from a slice.
        ranked = null;
        searchNote = `${data.total} sources here — more than ranking holds, so the server searches`;
        await load();
        return;
      }
      await applySearch();
      return;
    }
    const data = await inflight.run(() => api.sources(domainFilter, search, focus));
    if (!data) return;
    rows = data.rows;
    total = data.total;
    corpusTotal = data.corpus_total;
    indexStale = data.index_stale;
    searching = false;
  }

  /** Rank the pool with Pagefind. No request for the rows — they are already
   *  here — and one fragment fetch per row actually drawn. */
  async function applySearch() {
    if (!ranked) return load();
    if (!search.trim()) {
      marks = new Map();
      rows = pool.slice(0, PAGE);
      total = pool.length;
      searching = false;
      return;
    }
    const page = await ranked.page(search, focus, shown);
    // The pool is already narrowed by domain, so a ranked key outside it simply
    // finds no row — the correct answer, since Pagefind knows nothing about the
    // domain filter and should not have to.
    const byKey = new Map(pool.map((r) => [r.path, r]));
    const hits: SourceRow[] = [];
    const next = new Map<string, string>();
    for (const hit of page.hits) {
      const row = byKey.get(hit.key);
      if (!row) continue;
      hits.push(row);
      if (hit.excerpt) next.set(hit.key, hit.excerpt);
    }
    marks = next;
    rows = hits;
    total = page.total;
    searching = false;
  }

  /** Chips grouped by their declared type, so a row of them says what it IS.
   *  The operator had to infer "oh, the tags are strategies" from the labels —
   *  which they could only do because they already knew the corpus. The types
   *  are open (`strategy`, `topic`, `thesis`), so the heading is read from the
   *  data rather than hardcoded. */
  let focusGroups = $derived.by(() => {
    const by = new Map<string, FocusDef[]>();
    for (const f of meta?.focuses ?? []) {
      if (!by.has(f.type)) by.set(f.type, []);
      by.get(f.type)!.push(f);
    }
    return [...by.entries()];
  });

  let focusLabel = $derived(
    (meta?.focuses ?? []).find((f) => f.value === focus)?.label ?? ''
  );

  /** A `domains:` tag as the corpus declares it — "Adult Literacy & Numeracy",
   *  not `strategy:adult-literacy-numeracy`. Falls back to the raw value, since
   *  a tag naming a folder with no `index.md` is still a real tag. */
  function tagLabel(value: string): string {
    return (meta?.focuses ?? []).find((f) => f.value === value)?.label ?? value;
  }

  function toggleFocus(value: string) {
    focus = focus === value ? '' : value;
    tab = 'sources';
    load();
  }

  /** Draw more of the ranked results. A click, not a keystroke — so re-resolving
   *  the rows already shown is affordable, and the bundle's fragments are served
   *  immutable so the browser does not re-fetch them at all. */
  function showMore() {
    shown += RANKED_PAGE;
    applySearch();
  }

  // Server search costs a request that reads the corpus, so it waits. Ranked
  // search ranks rows already in hand and fetches one fragment per row drawn —
  // and those are served immutable, so a repeated query fetches nothing at all.
  // The long wait was buying something that is no longer being spent.
  const SETTLE_RANKED = 90;
  const SETTLE_SERVER = 160;

  function debounced() {
    clearTimeout(timer);
    panelOpen = search.trim().length > 0;
    searching = panelOpen;
    shown = RANKED_PAGE; // a new query starts at the top again
    timer = setTimeout(
      () => (ranked ? applySearch() : load()),
      ranked ? SETTLE_RANKED : SETTLE_SERVER
    );
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
    panelOpen = false;
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
    <!-- The mark stands in for the wordmark; the name stays as the accessible
         label, so a screen reader still hears "corpora". -->
    <h1><CorporaMark size={26} /></h1>
    <div class="searchbox" bind:this={searchBox}>
      <input
        bind:value={search}
        oninput={debounced}
        onfocus={() => (panelOpen = search.trim().length > 0)}
        type="search"
        placeholder={ranked
          ? 'Search — ranked, any word order…'
          : 'Search title, excerpt, or path…'}
      />
      {#if panelOpen && search.trim()}
        <SearchPanel
          {rows}
          {marks}
          {total}
          {searching}
          ranked={!!ranked}
          {tagLabel}
          onpick={view}
          onclose={closePanel}
        />
      {/if}
    </div>
    <div class="dom">
      <DomainCombo
        bind:value={domainFilter}
        domains={meta?.domains ?? []}
        anyLabel="All domains"
        placeholder="All domains — type to filter…"
        onchange={load}
      />
    </div>

    <!-- Top right, as in augment-it's shell: which corpus, then the mode. -->
    <div class="chrome">
      <WorkspaceMenu
        workspace={meta?.workspace ?? null}
        label={meta?.label ?? ''}
        writable={meta?.writable ?? false}
      />
      <ModeToggle />
    </div>
  </div>

  {#if (meta?.focuses ?? []).length}
    <!-- "Mainly look here." Prominent by design: this is the first thing you
         reach for when drafting against a strategy, and the labels are the
         corpus's own declared titles rather than slugs. -->
    {#each focusGroups as [kind, items] (kind)}
      <div class="focuses">
        <span class="kind">{kind}</span>
        {#each items as f (f.value)}
          <button
            class="focus"
            class:on={focus === f.value}
            title="{f.type}: {f.folder}"
            aria-pressed={focus === f.value}
            onclick={() => toggleFocus(f.value)}>{f.label}</button
          >
        {/each}
        {#if focus && items.some((i) => i.value === focus)}
          <button class="focus clear" onclick={() => toggleFocus(focus)}>clear</button>
        {/if}
      </div>
    {/each}
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

  {#if meta && (searchNote || indexStale)}
    <!-- The search index is allowed to be absent or behind; it is not allowed
         to be quietly wrong about it. An affordance appears only on a writable
         server, because offering a rebuild that would 403 is worse than none. -->
    <p class="ro idx">
      {#if indexStale}
        The index has not seen every source yet — those rows were read directly.
      {:else}
        {searchNote}
      {/if}
      {#if meta.writable}
        <button class="relink" onclick={reindex} disabled={reindexing}>
          {reindexing ? 'Rebuilding…' : 'Rebuild index'}
        </button>
      {/if}
    </p>
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
      {#if total !== corpusTotal}
        <strong>{total}</strong>
        {focusLabel ? `in ${focusLabel}` : 'matching'} · {corpusTotal} in the corpus{rows.length <
        total
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
            {#if marks.has(row.path)}
              <!-- The passage that matched, not the first 240 characters of the
                   body — which is the same opening paragraph on every source and
                   tells you nothing about why this one came back. Already
                   reduced to text plus <mark> by `safeExcerpt`. -->
              <div class="e">{@html marks.get(row.path)}</div>
            {:else if row.excerpt}
              <div class="e">{row.excerpt}</div>
            {/if}
            <div class="chips">
              {#each chips(row) as [text, on]}<span class="chip" class:on>{text}</span>{/each}
              {#if row.binary_key}
                <span class="chip" class:on={row.binary_state === 'present'}>
                  PDF {kb(row.binary_bytes)}{row.binary_optimized ? ' · optimized' : ''}
                </span>
              {/if}
            </div>
          </button>
          {#if row.domains.length}
            <!-- The `domains:` tags, which the row has always carried and the
                 card has never shown. Outside the card button because they are
                 controls in their own right — clicking one focuses it — and a
                 button inside a button is not markup. -->
            <div class="tags">
              {#each row.domains as d (d)}
                <button
                  class="tag"
                  class:on={focus === d}
                  aria-pressed={focus === d}
                  title={d}
                  onclick={() => toggleFocus(d)}>{tagLabel(d)}</button
                >
              {/each}
            </div>
          {/if}
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
    {#if rows.length < total}
      <p class="more">
        <button class="relink" onclick={ranked && search.trim() ? showMore : undefined}
          disabled={!ranked || !search.trim()}
        >Showing {rows.length} of {total}{ranked && search.trim() ? ' — show more' : ''}</button>
      </p>
    {/if}
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
  /* Pushed right and kept together, so the two chrome controls read as one
     cluster rather than as the tail of the search row. */
  .chrome { margin-left: auto; display: flex; align-items: center; gap: 6px; flex: 0 0 auto; }
  .capture { margin-top: 8px; }
  h1 { font-size: 13px; margin: 0; font-weight: 700; letter-spacing: 0; display: flex; align-items: center; }
  h1 span { color: var(--color-text-muted); font-weight: 400; }

  /* The control primitive is global, in tokens.css. Everything here states
     only what differs from it. */
  input[type='search'], .capture input:first-of-type { flex: 1; min-width: 200px; }
  .dom { width: 280px; flex: 0 0 auto; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-text-muted); flex: 0 0 auto; white-space: nowrap; }
  .check input { width: auto; min-width: 0; padding: 0; margin: 0; accent-color: var(--color-accent); }
  .ro { margin: 6px 0 0; font-size: 11px; color: var(--color-text-muted); }
  .idx { display: flex; align-items: center; gap: 8px; }
  /* Opts out of the global control primitive, like the tree rows do: a
     border and a field background here would read as a form, and this is a
     sentence with an action at the end of it. */
  .relink {
    border: none; background: none; padding: 0;
    font-size: 11px; color: var(--color-accent); cursor: pointer;
    text-decoration: underline; text-underline-offset: 2px;
  }
  .relink:disabled { color: var(--color-text-muted); cursor: default; text-decoration: none; }
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
  .focuses { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; padding: 6px 16px; }
  .focuses:last-of-type { border-bottom: 1px solid var(--color-border); padding-bottom: 8px; }
  /* The declared type, so a row of chips says what it is without a hover. */
  .kind { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--color-text-muted); min-width: 62px; }
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

  /* The panel anchors to this, so it has to establish the containing block. */
  .searchbox { position: relative; flex: 1 1 auto; min-width: 0; display: flex; }
  .searchbox input { width: 100%; }
  .more { margin: 12px 0 0; text-align: center; }
  .tags { display: flex; gap: 5px; flex-wrap: wrap; padding: 0 11px 8px; }
  .tag {
    font-size: 11px; padding: 1px 7px; width: auto;
    border-radius: var(--radius-pill);
    border: 1px solid var(--color-border);
    background: none; color: var(--color-accent); cursor: pointer;
  }
  .tag:hover { border-color: var(--color-accent); }
  .tag.on { background: var(--color-accent); border-color: var(--color-accent); color: var(--color-on-accent); }
  /* The matched terms. Tinted rather than the browser's yellow, which belongs
     to no mode this app has. */
  .e :global(mark) {
    background: color-mix(in oklab, var(--color-accent) 28%, transparent);
    color: var(--color-text);
    border-radius: 2px;
    padding: 0 1px;
  }

  .backdrop { position: fixed; inset: 0; background: var(--fx-scrim); display: grid; place-items: center; padding: 24px; }
  .modal { background: var(--color-surface); border: 1px solid var(--color-border-strong); border-radius: var(--radius-lg); max-width: min(880px, 94vw); width: 100%; }
  .mhead { border-bottom: 1px solid var(--color-border); padding: 9px 13px; }
  .mhead h1 { flex: 1; }
  pre { margin: 0; padding: 13px 15px; overflow: auto; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 66vh; }
</style>
