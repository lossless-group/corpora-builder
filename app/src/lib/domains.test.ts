/**
 * Covers `context-v/specs/Domain-Navigation.md`.
 *
 * `node --test` with native type-stripping — no test framework, no bundler, no
 * dependency added to run four hundred lines of assertions. Each test name
 * begins with its spec ID; `app/scripts/run-tests.mjs` reads those names and
 * writes `.spec-results.json` in the shape `scripts/spec_status.py` already
 * consumes, so frontend promises land in the same ledger as the Python ones.
 *
 * Fixtures are a real slice of reach-edu, not invented strings. The whole reason
 * this component exists is that `funders/` has 66 children.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { chopSegment, isNavigable, normalize, rank, score, splitForDisplay, words } from './domains.ts';

const DOMAINS = [
  '(root)',
  '_discarded',
  'academic-institutions/mit',
  'associations-networks/national-skills-coalition',
  'data-services/lightcast',
  'funders/annie-e-casey-foundation',
  'funders/ascendium-education',
  'funders/ballmer-group',
  'funders/hewlett-foundation',
  'funders/lumina-foundation',
  'funders/reach-edu-first-party',
  'funders/the-gates-foundation',
  'funders/walton-family-foundation',
  'gov-entities/us-department-of-labor',
  'inbox',
  'inbox/gated',
  'strategies',
  'strategies/workforce-development',
  'think-tanks/brookings',
  'topics/future-of-work',
];

// ---------------------------------------------------------------------------
// finding one
// ---------------------------------------------------------------------------

test('DOMAIN-01 casing and separators do not matter', () => {
  for (const q of [
    'Ascendium Education',
    'ascendium-education',
    'ASCENDIUM_EDUCATION',
    'ascendium education',
    'Ascendium  --  Education',
  ]) {
    assert.equal(rank(q, DOMAINS)[0], 'funders/ascendium-education', `query: ${q}`);
  }
});

test('DOMAIN-02 exact outranks prefix outranks word match', () => {
  assert.equal(score('inbox', 'inbox'), 100);
  assert.equal(score('inbox', 'inbox/gated'), 80);
  // 'gates' appears inside the-gates-foundation but starts neither the path nor
  // the last segment.
  assert.equal(score('gates', 'funders/the-gates-foundation'), 60);
  assert.ok(score('inbox', 'inbox') > score('inbox', 'inbox/gated'));
});

test('DOMAIN-03 the last segment matches without typing the parent', () => {
  assert.equal(rank('ascendium', DOMAINS)[0], 'funders/ascendium-education');
  assert.equal(rank('brookings', DOMAINS)[0], 'think-tanks/brookings');
  assert.equal(score('ascendium', 'funders/ascendium-education'), 70);
});

test('DOMAIN-04 every query word must appear', () => {
  assert.equal(score('gates rockefeller', 'funders/the-gates-foundation'), -1);
  assert.equal(score('walton family', 'funders/walton-family-foundation'), 70);
  // Order-independent: the words may appear in any order in the path.
  assert.equal(score('foundation gates', 'funders/the-gates-foundation'), 60);
});

test('DOMAIN-05 a dropped letter still finds it', () => {
  // "lumna" — the 'i' never typed. Not a prefix, not a word; a subsequence.
  assert.equal(score('lumna', 'funders/lumina-foundation'), 40);
  assert.equal(rank('lumna', DOMAINS)[0], 'funders/lumina-foundation');
});

test('DOMAIN-06 no match returns nothing, not everything', () => {
  assert.deepEqual(rank('zzzzqqq', DOMAINS), []);
});

test('DOMAIN-07 ties break by depth, then alphabetically', () => {
  // Broader scope first: one segment before two.
  assert.deepEqual(rank('strategies', DOMAINS), ['strategies', 'strategies/workforce-development']);
  assert.deepEqual(rank('inbox', DOMAINS), ['inbox', 'inbox/gated']);

  // Within one depth, strictly alphabetical — NOT by string length. Sorting 66
  // siblings by how long their names are is indistinguishable from random.
  const funders = rank('funders/', DOMAINS);
  assert.deepEqual(funders, [...funders].sort());
  assert.equal(funders[0], 'funders/annie-e-casey-foundation');
  assert.ok(funders.indexOf('funders/ballmer-group') > 0, 'shortest name must not float to the top');
});

test('DOMAIN-08 an empty query returns everything in path order', () => {
  assert.equal(rank('', DOMAINS).length, DOMAINS.length);
  assert.deepEqual(rank('   ', DOMAINS), rank('', DOMAINS));
});

// ---------------------------------------------------------------------------
// getting back out
// ---------------------------------------------------------------------------

test('DOMAIN-09 backspace walks the path a segment at a time', () => {
  assert.equal(chopSegment('funders/ascendium-education'), 'funders/');
  assert.equal(chopSegment('funders/'), '');
});

test('DOMAIN-10 a single segment goes straight to empty', () => {
  assert.equal(chopSegment('inbox'), '');
  assert.equal(chopSegment(''), '');
});

test('DOMAIN-11 navigable means a real domain or a real prefix', () => {
  assert.equal(isNavigable('funders/ascendium-education', DOMAINS), true);
  assert.equal(isNavigable('funders/', DOMAINS), true);
  assert.equal(isNavigable('inbox', DOMAINS), true);
  // Mid-typing and typos are NOT navigable — Backspace stays a Backspace.
  assert.equal(isNavigable('funders/ascend', DOMAINS), false);
  assert.equal(isNavigable('fund', DOMAINS), false);
  assert.equal(isNavigable('', DOMAINS), false);
});

test('DOMAIN-12 a prefix nothing sits under is not navigable', () => {
  assert.equal(isNavigable('nonexistent/', DOMAINS), false);
});

// ---------------------------------------------------------------------------
// display
// ---------------------------------------------------------------------------

test('DOMAIN-13 a row splits into a dimmable prefix and a remainder', () => {
  assert.deepEqual(splitForDisplay('funders/ascendium-education'), {
    prefix: 'funders/',
    rest: 'ascendium-education',
  });
  assert.deepEqual(splitForDisplay('inbox'), { prefix: '', rest: 'inbox' });
});

test('DOMAIN-14 separator runs collapse instead of emitting empty words', () => {
  assert.equal(normalize('  Ascendium --  Education  '), 'ascendium education');
  assert.equal(normalize('funders/ascendium-education'), 'funders ascendium education');
  assert.deepEqual(words(''), []);
  assert.deepEqual(words('   ---   '), []);
  assert.deepEqual(words('a/b'), ['a', 'b']);
});
