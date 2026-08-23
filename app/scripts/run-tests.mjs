#!/usr/bin/env node
/**
 * Run the frontend tests and write `.spec-results.json` in the shape
 * `scripts/spec_status.py` already consumes.
 *
 * Why this exists: the repo's whole discipline is that spec status is *derived
 * from execution*, never written by hand — see `context-v/loops/Spec-to-Shipped-With-TDD.md`.
 * Until now the ledger only saw pytest, so the first frontend spec would have
 * been a set of promises nothing could check, which is precisely the failure
 * mode the ledger exists to prevent. It would have reported MISSING and been
 * "fixed" by deleting the rows.
 *
 * The join is by convention: a test whose name begins with a spec ID
 * (`DOMAIN-07 ties break by …`) reports that ID's outcome. Zero dependencies —
 * node's own runner, node's own type-stripping.
 */
import { run } from 'node:test';
import { writeFileSync } from 'node:fs';
import { globSync } from 'node:fs';

const ROOT = new URL('..', import.meta.url).pathname;
const files = globSync('src/**/*.test.ts', { cwd: ROOT }).map((f) => ROOT + f);

if (files.length === 0) {
  console.error('  no frontend test files found — expected src/**/*.test.ts');
  process.exit(1);
}

const ID = /^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+)\b/;
const results = {};
let pass = 0;
let fail = 0;

function record(e, outcome) {
  outcome === 'passed' ? pass++ : fail++;
  const m = ID.exec(e.name);
  if (!m) return;
  const id = m[1];
  const entry = (results[id] ??= { outcome: 'passed', tests: [] });
  entry.tests.push({ nodeid: `app/${e.file?.replace(ROOT, '') ?? '?'}::${e.name}`, outcome });
  // Worst outcome wins, so one red test cannot be masked by a green sibling.
  if (outcome === 'failed') entry.outcome = 'failed';
  if (outcome === 'failed') console.error(`  ✗ ${e.name}`);
}

// `for await` rather than event listeners: the stream must actually be consumed
// or it never drains, and an unconsumed run exits 0 having reported nothing —
// a green build that ran no tests, which is the worst possible failure here.
for await (const event of run({ files, concurrency: true })) {
  if (event.type === 'test:pass') record(event.data, 'passed');
  else if (event.type === 'test:fail') record(event.data, 'failed');
}

writeFileSync(ROOT + '.spec-results.json', JSON.stringify(results, null, 2) + '\n');
const ids = Object.keys(results).length;
console.log(`  frontend: ${pass} passed · ${fail} failed · ${ids} spec ID(s) reported`);
process.exit(fail ? 1 : 0);
