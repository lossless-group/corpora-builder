/**
 * Ranked search over the Pagefind bundle the sidecar serves.
 *
 * Implements the client half of `context-v/specs/Ranked-Search.md`.
 *
 * **Pagefind does not replace the manifest.** It has no incremental add, so it
 * cannot be kept current on capture; the server's manifest-backed listing stays
 * the always-fresh answer. This is ranking on top of that, and it steps aside
 * whenever it cannot be trusted:
 *
 * - no bundle built  → the server searches
 * - bundle older than the manifest → the server searches, and the UI says why
 *
 * Serving stale ranking silently is worse than serving honest substring
 * matching, which is the whole reason `decideSearch` exists as its own function
 * rather than as an `if` buried in a component.
 */

/** The subset of Pagefind's browser API this app uses. */
export interface PagefindApi {
  options(opts: Record<string, unknown>): Promise<void>;
  search(
    query: string | null,
    opts?: { filters?: Record<string, string | string[]> }
  ): Promise<PagefindResponse>;
  filters(): Promise<Record<string, Record<string, number>>>;
}

export interface PagefindResponse {
  results: PagefindResult[];
  /** Counts per filter value WITHIN this query's matches — which is exactly the
   *  "12 in Workforce Development · 832 in the corpus" shape, for free. */
  filters?: Record<string, Record<string, number>>;
}

export interface PagefindResult {
  id: string;
  score: number;
  /** Fetches THIS result's fragment. One network round trip, every time — see
   *  `RankedSearch.page` for why that is the single most important fact here. */
  data(): Promise<PagefindData>;
}

export interface PagefindData {
  url: string;
  meta?: Record<string, string>;
  /** The matching passage, with `<mark>` around the terms that matched. This is
   *  what makes a result say WHY it matched rather than just that it did. */
  excerpt?: string;
  filters?: Record<string, string[]>;
}

/** One result, resolved. */
export interface RankedHit {
  key: string;
  title: string;
  /** Sanitised excerpt — text plus `<mark>`, nothing else. */
  excerpt: string;
  score: number;
  focuses: string[];
}

export interface RankedPage {
  /** Every match, counted without resolving any of them. */
  total: number;
  /** Only the ones being drawn. */
  hits: RankedHit[];
}

/**
 * Pagefind's excerpt, reduced to text and `<mark>`.
 *
 * Pagefind escapes fragment content and inserts only `<mark>`, so this is a
 * belt to its braces — but the string is rendered as HTML, and "the library
 * escapes it" is a claim that stops being true the day the library changes.
 * Every other tag goes, attributes and all: `<mark foo>` is not `<mark>`.
 */
export function safeExcerpt(raw: string): string {
  return raw.replace(/<(?!\/?mark>)[^>]*>/g, '');
}

export interface Bundle {
  api: PagefindApi;
  /** The manifest fingerprint this bundle was built from. */
  fingerprint: string;
}

export type SearchMode = 'ranked' | 'server';

export interface SearchDecision {
  mode: SearchMode;
  /** Empty when ranked. Otherwise why the bundle was passed over, in words a
   *  person can read — this reaches the UI, not just a log. */
  reason: string;
}

/**
 * Whether ranked search can be trusted right now.
 *
 * A content fingerprint rather than a timestamp: reindexing an unchanged corpus
 * must not make every bundle look stale, and clock skew between a laptop and a
 * bucket is not a thing worth debugging.
 */
export function decideSearch(
  bundle: Bundle | null,
  manifestFingerprint: string
): SearchDecision {
  if (!bundle) return { mode: 'server', reason: 'no search index built yet' };
  if (!manifestFingerprint) return { mode: 'server', reason: 'the corpus is not indexed' };
  if (bundle.fingerprint !== manifestFingerprint) {
    return { mode: 'server', reason: 'the search index is older than the corpus — reindex to rank' };
  }
  return { mode: 'ranked', reason: '' };
}

/**
 * Whether the rows held client-side cover everything the current filter selects.
 *
 * `selected` is the CURRENT listing's total — what the domain and focus narrow
 * to — never the corpus total. Comparing against the corpus stood ranking down
 * the moment any focus chip was clicked: 41 rows held, 847 in the corpus, and
 * the two were never going to match.
 *
 * Ranked search works against rows already fetched, which is what makes it
 * instant. That only stays *correct* while those rows are all of them: a hit
 * ranked outside the fetched window has no row to render, so it would silently
 * vanish rather than merely rank low.
 *
 * A silent cap reads as "covered everything" when it did not, so this is a
 * function with a name rather than a comparison buried in a component — and
 * when it returns false the app says so and lets the server search.
 */
export function poolCoversCorpus(poolSize: number, selected: number): boolean {
  return poolSize >= selected;
}

/**
 * The corpus key a Pagefind hit refers to.
 *
 * Read from `meta.path` rather than from `url`, because Pagefind computes a
 * result URL from its own base path and the record's URL — so the only string
 * guaranteed to come back as the corpus key is the one the builder put in the
 * metadata itself.
 */
export function keyOf(data: { url: string; meta?: Record<string, string> }): string {
  return data.meta?.path ?? data.url.replace(/^\/+/, '');
}

/** Ranked search against one loaded bundle. */
export class RankedSearch {
  // A plain field rather than a constructor parameter property: node's
  // type-stripping is strip-only, and a parameter property is the one piece of
  // TypeScript that emits code rather than erasing it. `node --test` is the
  // gate here, so the syntax that gate cannot read is syntax this app cannot use.
  readonly api: PagefindApi;

  /** Pagefind loads its filter index lazily. Until something asks for the
   *  filters, `search()` reports every count as absent — measured, not read in
   *  a doc: an identical query returns `{}` before `filters()` has been called
   *  and real counts after. Kept as a promise so concurrent callers share one
   *  fetch rather than racing to trigger it. */
  #filtersReady: Promise<unknown> | null = null;

  constructor(api: PagefindApi) {
    this.api = api;
  }

  async #readyForCounts(): Promise<void> {
    if (!this.#filtersReady) this.#filtersReady = this.api.filters();
    await this.#filtersReady;
  }

  /**
   * One page of results, best first, with the passage that matched.
   *
   * **Resolve only what you draw.** `data()` fetches that result's fragment —
   * one round trip each. Resolving every match cost 615 fetches and 821ms for a
   * single query on an 845-source corpus, measured against local files; over
   * HTTP to the sidecar it is worse. The count comes from `results.length`,
   * which needs no fetch at all, and only the visible page is resolved — in
   * parallel, because they are independent.
   *
   * `focus` goes through Pagefind's FILTER rather than the query text. A tag
   * like `strategy:adult-literacy-numeracy` is not prose — routed through the
   * text index it would be tokenised and stemmed, and an exact tag would stop
   * being exact.
   */
  async page(query: string, focus = '', limit = 50): Promise<RankedPage> {
    const res = await this.api.search(
      query.trim() ? query : null,
      focus ? { filters: { focus } } : undefined
    );
    const hits = await Promise.all(
      res.results.slice(0, limit).map(async (hit) => {
        const d = await hit.data();
        return {
          key: keyOf(d),
          title: d.meta?.title ?? '',
          excerpt: safeExcerpt(d.excerpt ?? ''),
          score: hit.score,
          focuses: d.filters?.focus ?? []
        };
      })
    );
    return { total: res.results.length, hits };
  }

  /** Matching corpus keys, best first. A thin read over `page`. */
  async keys(query: string, focus = '', limit = 50): Promise<string[]> {
    return (await this.page(query, focus, limit)).hits.map((h) => h.key);
  }

  /**
   * How many sources each focus holds for this query.
   *
   * This is the `"12 in Workforce Development · 832 in the corpus"` shape the
   * app already builds by hand, arriving for free — and it is why the focuses
   * are filters rather than query text.
   *
   * `keys()` deliberately does NOT wait on the filter index: filtering itself
   * loads whatever it needs, and making every search wait for counts nobody
   * asked for would be a round trip spent on nothing.
   */
  async focusCounts(query: string): Promise<Record<string, number>> {
    await this.#readyForCounts();
    const res = await this.api.search(query.trim() ? query : null);
    return res.filters?.focus ?? {};
  }
}

/**
 * Load the bundle the sidecar serves, or `null` when none is built.
 *
 * The dynamic import is deliberately opaque to the bundler: Pagefind's runtime
 * is generated at index time and fetched at run time, so Vite must not try to
 * resolve it. Without the hint the build fails in a way that reads like a
 * missing dependency.
 */
export async function loadBundle(base: string, fingerprint: string): Promise<Bundle | null> {
  if (!fingerprint) return null;
  const root = base.endsWith('/') ? base : `${base}/`;
  try {
    const api = (await import(/* @vite-ignore */ `${root}pagefind.js`)) as unknown as PagefindApi;
    await api.options({ basePath: root });
    return { api, fingerprint };
  } catch {
    return null;
  }
}
