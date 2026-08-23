/**
 * Covers `context-v/specs/Browse-Corpus.md` BROWSE-17.
 *
 * The scenario is the reported one, reproduced with controlled timing: a slow
 * search still in flight when a fast one is issued. Real timings from the
 * running app — 5.8s for `search=grant`, 0.48s for an unsearched page.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { Latest } from './latest.ts';

const after = <T>(ms: number, value: T): Promise<T> =>
  new Promise((res) => setTimeout(() => res(value), ms));

test('BROWSE-17 a slow earlier response never overwrites a fast later one', async () => {
  const latest = new Latest();
  const landed: (string | undefined)[] = [];

  // "grant" — a search, so the server reads every file. Slow.
  const slow = latest.run(() => after(40, 'results for grant')).then((v) => landed.push(v));
  // The operator clears the box. Unsearched page, fifty reads. Fast.
  const fast = latest.run(() => after(5, 'everything')).then((v) => landed.push(v));

  await Promise.all([slow, fast]);

  // Both settled; the fast one first, and the stale slow one was dropped.
  assert.deepEqual(landed, ['everything', undefined]);
});

test('BROWSE-17 the newest request always wins, whatever the order of arrival', async () => {
  const latest = new Latest();
  const results = await Promise.all([
    latest.run(() => after(30, 'first')),
    latest.run(() => after(20, 'second')),
    latest.run(() => after(10, 'third')),
  ]);

  assert.deepEqual(results, [undefined, undefined, 'third']);
});

test('BROWSE-17 a stale rejection is dropped but a current one still throws', async () => {
  const latest = new Latest();

  const stale = latest.run(() => Promise.reject(new Error('gone')));
  const fresh = latest.run(() => after(5, 'ok'));

  assert.equal(await stale, undefined, 'a failure nobody is waiting on is not an error');
  assert.equal(await fresh, 'ok');

  // The current request's failure must surface — silently swallowing it would
  // leave the operator staring at stale rows with no indication anything broke.
  await assert.rejects(() => latest.run(() => Promise.reject(new Error('boom'))), /boom/);
});
