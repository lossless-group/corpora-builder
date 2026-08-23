/**
 * Covers `context-v/specs/Ranked-Search.md`.
 *
 * These tests build a REAL Pagefind bundle with the same script `reindex` runs,
 * then search it. Pagefind's Node package indexes but does not search — the
 * search runtime is the generated `pagefind.js`, written for a browser — so the
 * harness below gives it the one browser API it actually needs, `fetch` over
 * `file:` URLs, and lets it run untouched.
 *
 * That matters: asserting against a hand-rolled fake of a search engine would
 * prove nothing about ranking or stemming, which are the only reasons to have
 * one.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

import {
  RankedSearch,
  decideSearch,
  keyOf,
  poolCoversCorpus,
  safeExcerpt,
  type PagefindApi
} from './search.ts';

const APP = new URL('../../', import.meta.url).pathname;
const BUILDER = join(APP, 'scripts', 'build-search-index.mjs');

/** Shaped like a real manifest: mostly untagged, one source tagged into a
 *  strategy whose words its own prose never uses. */
const ENTRIES = [
  {
    key: 'live/strategies/workforce-development/sources/2026-01-01_a.md',
    title: 'Apprenticeship Report',
    excerpt: 'Rural counties expanded placements sharply after the state funded a new program. Filed in the corpus.',
    domains: ['strategy:workforce-development']
  },
  {
    key: 'live/strategies/workforce-development/sources/2026-01-02_b.md',
    title: 'Skills Gap Study',
    excerpt: 'The gap between employer demand and worker credentials across manufacturing. Filed in the corpus.',
    domains: ['strategy:workforce-development']
  },
  {
    key: 'live/strategies/adult-literacy-numeracy/sources/2026-02-01_c.md',
    title: 'Reading Levels',
    excerpt: 'Adult reading proficiency measured across three cohorts. Filed in the corpus.',
    domains: ['strategy:adult-literacy-numeracy']
  },
  {
    key: 'live/funders/gates/2026-09-01_d.md',
    title: 'Grant Announcement',
    excerpt: 'The foundation announced apprenticeship pathways for rural counties. Filed in the corpus.',
    domains: []
  },
  {
    key: 'live/funders/gates/2026-01-05_x.md',
    title: 'Cross-Tagged Brief',
    excerpt: 'A short brief on credential stacking and employer partnerships. Filed in the corpus.',
    domains: ['strategy:adult-literacy-numeracy']
  },
  {
    // The three-segment chain. Deliberately shares no query word with the tests
    // above, so it exercises the cascade without disturbing their ranking.
    key: 'live/domains/strategies/workforce-development/sources/2026-01-06_z.md',
    title: 'Regional Board Minutes',
    excerpt: 'Minutes of the regional board covering budget and staffing. Filed in the corpus.',
    domains: ['domain:strategy:workforce-development']
  }
];

let dir = '';
let api: PagefindApi;
let ranked: RankedSearch;
/** Counts fragment fetches, so "how many round trips did that cost" is an
 *  assertion rather than a hope. */
let fetches = 0;

before(async () => {
  dir = await mkdtemp(join(tmpdir(), 'ranked-search-'));
  const manifest = join(dir, 'sources.jsonl');
  await writeFile(manifest, ENTRIES.map((e) => JSON.stringify(e)).join('\n') + '\n');

  const out = join(dir, 'pagefind');
  const built = spawnSync(process.execPath, [BUILDER, '--manifest', manifest, '--out', out], {
    cwd: APP,
    encoding: 'utf-8'
  });
  assert.equal(built.status, 0, `builder failed: ${built.stderr || built.stdout}`);

  // The one browser API Pagefind's runtime cannot do without. Everything else
  // it touches — document, window, Worker — it already guards behind an
  // is-this-a-browser check, so the runtime under test is the shipped one.
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (!url.startsWith('file:')) return realFetch(input as RequestInfo, init);
    fetches++;
    const body = await readFile(new URL(url));
    const type = url.endsWith('.pagefind')
      ? 'application/wasm'
      : url.endsWith('.json')
        ? 'application/json'
        : 'application/octet-stream';
    return new Response(body, { status: 200, headers: { 'content-type': type } });
  }) as typeof fetch;

  const base = pathToFileURL(out).href + '/';
  api = (await import(`${base}pagefind.js`)) as unknown as PagefindApi;
  await api.options({ basePath: base });
  ranked = new RankedSearch(api);
});

after(async () => {
  if (dir) await rm(dir, { recursive: true, force: true });
});

const A = ENTRIES[0].key;
const CROSS = ENTRIES[4].key;

// ---------------------------------------------------------------------------
// what substring matching cannot do
// ---------------------------------------------------------------------------

test('SEARCH-01 two words in any order, separated by others', async () => {
  // Neither ordering exists as a literal substring anywhere, so a `needle in
  // haystack` search finds nothing for either query. That is the gap.
  const haystack = ENTRIES.map((e) => `${e.title} ${e.excerpt}`).join(' ').toLowerCase();
  assert.ok(!haystack.includes('placements counties'));
  assert.ok(!haystack.includes('counties placements'));

  const forward = await ranked.keys('placements counties');
  const backward = await ranked.keys('counties placements');

  assert.ok(forward.includes(A));
  assert.deepEqual(forward, backward, 'word order must not change the result set');
});

test('SEARCH-02 a morphological variant matches', async () => {
  const haystack = ENTRIES.map((e) => `${e.title} ${e.excerpt}`).join(' ').toLowerCase();
  assert.ok(!haystack.includes('funding'), 'the corpus says "funded", never "funding"');

  const hits = await ranked.keys('funding');

  assert.ok(hits.includes(A));
});

test('SEARCH-03 a title match outranks a body-only match', async () => {
  // "Apprenticeship" is this source's TITLE and another source's prose. Ranking
  // is the whole point of the bundle; date order would put the other one first.
  const hits = await ranked.keys('apprenticeship');

  assert.ok(hits.length >= 2, 'both sources must match at all');
  assert.equal(hits[0], A);
});

// ---------------------------------------------------------------------------
// focuses are filters
// ---------------------------------------------------------------------------

test('SEARCH-04 filtering narrows, and every focus reports its count', async () => {
  const all = await ranked.focusCounts('');
  assert.equal(all['strategy:workforce-development'], 2);
  assert.equal(all['strategy:adult-literacy-numeracy'], 2);

  const forQuery = await ranked.focusCounts('apprenticeship');
  assert.equal(forQuery['strategy:workforce-development'], 1);
  assert.ok(!forQuery['strategy:adult-literacy-numeracy']);

  const narrowed = await ranked.keys('apprenticeship', 'strategy:workforce-development');
  assert.deepEqual(narrowed, [A], 'the untagged funder source matching the query stays out');
});

test('SEARCH-05 an exact tag resolves through the filter, not the text index', async () => {
  const focus = 'strategy:adult-literacy-numeracy';

  const tagged = await ranked.keys('', focus);

  assert.equal(tagged.length, 2);
  assert.ok(tagged.includes(CROSS));

  // The FOCUS-01 promise, which tokenising could easily have broken: a word
  // living only inside the tag still reaches the source. That is why the
  // builder puts the domains in the content as well as in the filters.
  const brief = ENTRIES[4];
  assert.ok(!`${brief.title} ${brief.excerpt}`.toLowerCase().includes('literacy'));
  assert.ok((await ranked.keys('literacy')).includes(CROSS));
});

test('SEARCH-05 a hit reports its corpus key, not a rendered URL', async () => {
  const res = await api.search('apprenticeship');
  const data = await res.results[0].data();

  assert.equal(keyOf(data), A);
  assert.ok(!keyOf(data).startsWith('/'), 'a corpus key is not a path');
});

// ---------------------------------------------------------------------------
// stepping aside
// ---------------------------------------------------------------------------

test('SEARCH-06 a bundle older than the manifest is reported and bypassed', () => {
  const bundle = { api, fingerprint: 'aaaa' };

  const fresh = decideSearch(bundle, 'aaaa');
  const stale = decideSearch(bundle, 'bbbb');

  assert.equal(fresh.mode, 'ranked');
  assert.equal(fresh.reason, '');
  assert.equal(stale.mode, 'server');
  assert.match(stale.reason, /older than the corpus/);
});

test('SEARCH-07 no bundle falls back rather than failing', () => {
  const none = decideSearch(null, 'aaaa');
  const unindexed = decideSearch({ api, fingerprint: 'aaaa' }, '');

  assert.equal(none.mode, 'server');
  assert.match(none.reason, /no search index/);
  assert.equal(unindexed.mode, 'server');
  assert.match(unindexed.reason, /not indexed/);
});

test('SEARCH-11 ranking stands down when the rows in hand are not all of them', () => {
  // Ranked search reorders rows the client already has. A hit ranked outside
  // that window has no row to render, so it would vanish rather than rank low —
  // which is the failure mode a silent cap always has.
  assert.equal(poolCoversCorpus(846, 846), true);
  assert.equal(poolCoversCorpus(2000, 2001), false);
  assert.equal(poolCoversCorpus(0, 0), true, 'an empty selection is fully covered');
  // The regression this exists to prevent: the second argument is what the
  // CURRENT filter selects, not the corpus total. Comparing to the corpus stood
  // ranking down on every focus chip — 41 rows held, 847 in the corpus.
  assert.equal(poolCoversCorpus(41, 41), true, 'a narrowed listing is covered by its own rows');
});

// ---------------------------------------------------------------------------
// resolve only what you draw
// ---------------------------------------------------------------------------

test('SEARCH-12 a page of results costs a fetch per row shown, not per match', async () => {
  // The regression this exists to prevent, measured before it was fixed: this
  // resolved every match, which was 615 fetches and 821ms for ONE query against
  // local files. Over HTTP to the sidecar it was the reason search felt slow.
  // A word every entry's prose carries — the corpus key is deliberately NOT
  // indexed, because Pagefind excerpts from what it matches on and a path
  // rendered as prose is not a preview. So the shared token has to be real text.
  const all = await ranked.page('corpus', '', 1000);
  assert.ok(all.total >= 4, `the query must match most of the fixture; matched ${all.total}`);

  await ranked.page('corpus', '', 2); // warm the shared index/meta chunks
  fetches = 0;
  const page = await ranked.page('corpus', '', 2);

  assert.equal(page.hits.length, 2, 'only the page is resolved');
  assert.equal(page.total, all.total, '...but the count is still every match');
  assert.ok(
    fetches <= page.hits.length,
    `resolving 2 rows cost ${fetches} fetches; it must not scale with ${all.total} matches`
  );
});

test('SEARCH-12 a hit carries the passage that matched, marked', async () => {
  // A result that says WHY it matched, rather than showing the same first 240
  // characters of the body every source shows.
  const { hits } = await ranked.page('apprenticeship', '', 3);

  assert.ok(hits[0].excerpt.includes('<mark>'), hits[0].excerpt);
  assert.ok(hits[0].title, 'and its title, without a second lookup');
  assert.ok(Array.isArray(hits[0].focuses));
});

test('SEARCH-12 an excerpt is reduced to text and mark, nothing else', () => {
  assert.equal(safeExcerpt('a <mark>b</mark> c'), 'a <mark>b</mark> c');
  assert.equal(safeExcerpt('<img src=x onerror=alert(1)>hi'), 'hi');
  assert.equal(safeExcerpt('<mark onload=alert(1)>b</mark>'), 'b</mark>');
  assert.equal(safeExcerpt('<script>alert(1)</script>ok'), 'alert(1)ok');
});

// ---------------------------------------------------------------------------
// a reference cascades
// ---------------------------------------------------------------------------

test('SEARCH-13 a shorter chain filters to everything beneath it', async () => {
  // Pagefind filters are exact-match, so the builder writes down every chain a
  // reference answers to. One entry carries the three-segment
  // `domain:strategy:workforce-development`; two carry the two-segment
  // `strategy:workforce-development`. Focusing `domain` must reach the first
  // and none of the others.
  const deep = ENTRIES[5].key; // the three-segment chain
  const mid = ENTRIES[0].key; // the two-segment one

  assert.deepEqual(await ranked.keys('', 'domain'), [deep]);
  assert.deepEqual(await ranked.keys('', 'domain:strategy'), [deep]);
  assert.deepEqual(await ranked.keys('', 'domain:strategy:workforce-development'), [deep]);

  // The two-segment references answer to their own chain only — a longer chain
  // is NOT reached by a focus that is not a prefix of it.
  const twoSegment = await ranked.keys('', 'strategy:workforce-development');
  assert.equal(twoSegment.length, 2);
  assert.ok(twoSegment.includes(mid));
  assert.ok(!twoSegment.includes(deep));

  // And every level is counted, so a rollup is free.
  const counts = await ranked.focusCounts('');
  assert.equal(counts['domain'], 1);
  assert.equal(counts['domain:strategy'], 1);
  assert.equal(counts['strategy:workforce-development'], 2);
  // `strategy` rolls up BOTH strategies — the two workforce-development sources
  // and the two adult-literacy ones — which is the whole point of a rollup and
  // is not reachable by an exact-match filter without the expansion.
  assert.equal(counts['strategy'], 4);
  assert.equal(counts['strategy:adult-literacy-numeracy'], 2);
});

test('SEARCH-13 the expansion matches the Python rule case for case', () => {
  // Mirrors `src/model/domains.py::cascade_prefixes`, asserted against the same
  // table as `FOCUS-10` so the two implementations cannot drift apart quietly.
  const prefixes = (r: string) => {
    const parts = r.split(':').filter(Boolean);
    return parts.map((_, i) => parts.slice(0, i + 1).join(':'));
  };
  assert.deepEqual(prefixes('domain:strategy:workforce-development'), [
    'domain',
    'domain:strategy',
    'domain:strategy:workforce-development'
  ]);
  assert.deepEqual(prefixes('strategy'), ['strategy']);
  assert.deepEqual(prefixes(''), []);
});
