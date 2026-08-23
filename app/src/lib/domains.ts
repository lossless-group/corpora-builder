/**
 * Domain matching and path-segment navigation.
 *
 * Implements `context-v/specs/Domain-Navigation.md`. Pure functions, no DOM —
 * the component that uses them is a thin shell, because the rules here are the
 * part that will silently rot and the part worth testing.
 *
 * Three ideas, in order of how much they matter:
 *
 * 1. **Normalise before comparing.** A funder's name arrives from the world as
 *    `Ascendium Education`; the folder is `ascendium-education`. Lowercasing and
 *    collapsing every non-alphanumeric run to a single space makes those the same
 *    string, and makes `/` just another separator — so `funders ascendium` and
 *    `funders/ascendium` are also the same query.
 *
 * 2. **Rank, don't just filter.** Forty alphabetical hits is not an answer. Five
 *    tiers, exact through subsequence, with the loosest tier last so it never
 *    outranks something you actually spelled correctly.
 *
 * 3. **Backspace is a function of the text, not of a mode.** `isNavigable` asks
 *    the corpus whether the current value names something real. No `justSelected`
 *    flag: a boolean set by one event and read by another is a thing that can be
 *    wrong, and the operator would have no way to see that it was.
 */

/** Lowercase; every run of non-alphanumerics becomes one space. `/` included. */
export function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

/** Normalised words. `''` yields `[]`, never `['']` — DOMAIN-14. */
export function words(s: string): string[] {
  const n = normalize(s);
  return n ? n.split(' ') : [];
}

/** Is `needle` a subsequence of `haystack`? Both should be normalised first. */
function isSubsequence(needle: string, haystack: string): boolean {
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i++;
    if (i === needle.length) return true;
  }
  return i === needle.length;
}

/** The last path segment, normalised. */
function lastSegment(domain: string): string {
  const i = domain.lastIndexOf('/');
  return normalize(i === -1 ? domain : domain.slice(i + 1));
}

export const NO_MATCH = -1;

/**
 * How well `query` matches `domain`. Higher is better; `NO_MATCH` excludes.
 *
 * The tiers are far apart on purpose. A gap of 10 would let two tie-breaks add
 * up to a tier jump, which is how a "smart" ranker starts putting the wrong row
 * first and nobody can say why.
 */
export function score(query: string, domain: string): number {
  const q = normalize(query);
  if (!q) return 0;
  const d = normalize(domain);

  if (d === q) return 100;
  if (d.startsWith(q)) return 80;
  if (lastSegment(domain).startsWith(q)) return 70;

  const qw = words(query);
  if (qw.every((w) => d.includes(w))) return 60;

  // The "near match for anything" rung: survives dropped letters, which is what
  // a typo usually is. Spaces are stripped so word boundaries do not block it.
  if (isSubsequence(q.replace(/ /g, ''), d.replace(/ /g, ''))) return 40;

  return NO_MATCH;
}

/**
 * Matching domains, best first — DOMAIN-02, DOMAIN-07, DOMAIN-08.
 *
 * Ties break by **depth**, then alphabetically. Broad before narrow is the order
 * you want when you are unsure, so `strategies` precedes
 * `strategies/workforce-development`.
 *
 * Depth, emphatically not string length. An earlier draft sorted ties by
 * `domain.length` on the same "shorter is broader" reasoning, which is true
 * across depths and meaningless within one: it put `funders/`'s sixty-six
 * children in the order ecmc, blackrock, bridgespan, judy-dimon, todd-fisher —
 * alphabetically random, which is the exact complaint this component exists to
 * answer. Caught by rendering the list, not by reading the comparator.
 */
const depth = (d: string): number => d.split('/').length;

export function rank(query: string, domains: readonly string[]): string[] {
  return domains
    .map((domain) => ({ domain, s: score(query, domain) }))
    .filter((m) => m.s !== NO_MATCH)
    .sort(
      (a, b) =>
        b.s - a.s || depth(a.domain) - depth(b.domain) || a.domain.localeCompare(b.domain),
    )
    .map((m) => m.domain);
}

/**
 * One segment back — DOMAIN-09, DOMAIN-10.
 *
 *   funders/ascendium-education  →  funders/  →  ''
 *   inbox                        →  ''
 *
 * The trailing slash is kept because it is what makes the *next* press chop
 * again rather than delete a character: `funders/` is still navigable.
 */
export function chopSegment(value: string): string {
  const v = value.endsWith('/') ? value.slice(0, -1) : value;
  const i = v.lastIndexOf('/');
  return i === -1 ? '' : v.slice(0, i + 1);
}

/**
 * Does `value` name something real — a domain, or a prefix some domain sits
 * under? DOMAIN-11, DOMAIN-12.
 *
 * This is the whole condition for segment-wise Backspace. If it is false the key
 * behaves exactly as the operator expects a Backspace to behave, which is the
 * point: the special case only fires where it is obviously wanted.
 */
export function isNavigable(value: string, domains: readonly string[]): boolean {
  if (!value) return false;
  if (domains.includes(value)) return true;
  return value.endsWith('/') && domains.some((d) => d.startsWith(value));
}

/**
 * Split a row for display — DOMAIN-13. The shared prefix is dimmed so the eye
 * reads the part that differs, rather than `funders/` sixty-six times.
 */
export function splitForDisplay(domain: string): { prefix: string; rest: string } {
  const i = domain.lastIndexOf('/');
  return i === -1
    ? { prefix: '', rest: domain }
    : { prefix: domain.slice(0, i + 1), rest: domain.slice(i + 1) };
}
