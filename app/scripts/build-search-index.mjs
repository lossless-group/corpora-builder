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
 * The `domains:` tags are here AS WELL AS in the filters, deliberately. As
 * filters they narrow exactly and report counts; as text their words stay
 * searchable, which is what keeps the `FOCUS-01` promise alive — typing
 * "literacy" has to reach a source tagged `strategy:adult-literacy-numeracy`
 * even though neither its title nor its excerpt says the word.
 *
 * The path is included for the same reason: the manifest's own search matches
 * it, and a bundle that quietly matched less would be a downgrade wearing a
 * feature's clothes.
 */
function content(entry) {
  return [
    entry.title ?? '',
    entry.excerpt ?? '',
    (entry.domains ?? []).join(' '),
    entry.key.replace(/[/_-]/g, ' '),
    entry.key
  ]
    .filter(Boolean)
    .join('\n');
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
    filters: { focus: entry.domains ?? [] }
  });
  if (res.errors?.length) errors.push(`${entry.key}: ${res.errors.join('; ')}`);
}

const written = await index.writeFiles({ outputPath: outPath });
if (written.errors?.length) errors.push(...written.errors);
await pagefind.close();

console.log(JSON.stringify({ records: entries.length, errors }));
process.exit(errors.length ? 1 : 0);
