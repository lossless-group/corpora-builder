#!/usr/bin/env node
/**
 * Build a Pagefind bundle from the source manifest.
 *
 * Implements the build half of `context-v/specs/Ranked-Search.md`.
 *
 * **It indexes the manifest, not the corpus.** One extract, two consumers: the
 * listing reads the manifest for rows, this reads it for search. Nothing here
 * opens a source file, so building the search index costs whatever the manifest
 * already cost and nothing more.
 *
 * It also knows nothing about R2. Python hands it a manifest on disk and takes
 * the output directory back, which is what keeps the storage seam intact — a
 * Node script that learned to talk to a bucket would be a second implementation
 * of `CorpusStore` nobody tested.
 *
 *   node scripts/build-search-index.mjs --manifest <path.jsonl> --out <dir>
 *
 * Prints one line of JSON to stdout: `{"records": N, "errors": [...]}`.
 */
import * as pagefind from 'pagefind';
import { readFileSync } from 'node:fs';

function arg(name) {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1 || i === process.argv.length - 1) {
    console.error(`missing --${name}`);
    process.exit(2);
  }
  return process.argv[i + 1];
}

const manifestPath = arg('manifest');
const outPath = arg('out');

const entries = readFileSync(manifestPath, 'utf-8')
  .split('\n')
  .filter((line) => line.trim())
  .map((line) => JSON.parse(line))
  .filter((e) => e && e.key);

const { index, errors: initErrors } = await pagefind.createIndex({
  // A corpus key is not prose. Without these, `strategy:workforce-development`
  // is torn apart at the colon and the hyphens before it ever reaches the
  // filter, and an exact tag search stops being exact.
  includeCharacters: ':-_/.'
});
if (initErrors?.length) {
  console.error(initErrors.join('\n'));
  process.exit(1);
}

/**
 * What Pagefind gets to read for a source.
 *
 * **Pagefind excerpts from the same text it matches on, so this is not just an
 * index — it is what a reader ends up looking at.** A first version also fed in
 * the corpus key, raw and de-punctuated, so that typing part of a path would
 * rank a source. It worked, and every result then displayed
 * `live strategies adult literacy numeracy sources 2026 05 06 source 089.md`
 * as though it were prose. Content indexed for MATCHING has to be content worth
 * READING, or the excerpt stops being one.
 *
 * So the key is gone from here — it lives in `meta.path`, which is what the app
 * joins on — and the loss is small, because a source filename in this corpus is
 * a slug of its own title and the title is indexed.
 *
 * The `domains:` REFERENCES stay, as WORDS rather than raw: `strategy:
 * adult-literacy-numeracy` becomes "adult literacy numeracy". As filters they
 * narrow exactly and report counts; as words they keep the `FOCUS-01` promise
 * alive — typing "literacy" has to reach a source carrying that tag even when
 * neither its title nor its excerpt says the word — and if they do surface in
 * an excerpt they read as English instead of as a slug.
 */
/**
 * Every chain a reference answers to, shortest first.
 *
 * `strategy:workforce-development` → `["strategy", "strategy:workforce-development"]`
 *
 * Pagefind filters are exact-match, so a cascade it knows nothing about has to
 * be written down in advance. Expanding here is what lets focusing `strategy`
 * return everything beneath it.
 *
 * Mirrors `src/model/domains.py::cascade_prefixes`. Two implementations of a
 * three-line rule, deliberately — the alternative is a shared package across a
 * Python sidecar and a Node builder. Both are covered by the same case table:
 * `FOCUS-09`/`FOCUS-10` on the Python side, `SEARCH-13` here.
 */
function cascadePrefixes(reference) {
  const parts = reference.split(':').filter(Boolean);
  return parts.map((_, i) => parts.slice(0, i + 1).join(':'));
}

function content(entry) {
  const referenceWords = (entry.domains ?? [])
    .map((d) => d.split(':').pop().replace(/[-_]/g, ' '))
    .join(' ');
  return [entry.title ?? '', entry.excerpt ?? '', referenceWords].filter(Boolean).join('\n');
}

const errors = [];
for (const entry of entries) {
  const res = await index.addCustomRecord({
    url: entry.key,
    content: content(entry),
    language: 'en',
    // `path` rather than the returned URL: Pagefind computes a result URL from
    // its own base and the record URL, so the only string guaranteed to come
    // back as the corpus key is one we put in the metadata ourselves.
    meta: { title: entry.title || entry.key.split('/').pop(), path: entry.key },
    // Expanded, so focusing a shorter chain filters correctly — see
    // `cascadePrefixes`. A reference contributes every chain it answers to.
    filters: { focus: [...new Set((entry.domains ?? []).flatMap(cascadePrefixes))] }
  });
  if (res.errors?.length) errors.push(`${entry.key}: ${res.errors.join('; ')}`);
}

const written = await index.writeFiles({ outputPath: outPath });
if (written.errors?.length) errors.push(...written.errors);
await pagefind.close();

console.log(JSON.stringify({ records: entries.length, errors }));
process.exit(errors.length ? 1 : 0);
