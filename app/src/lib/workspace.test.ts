/** Covers `context-v/specs/Header-Chrome.md` HEADER-06. */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { workspaceLabel, workspaceStorage } from './workspace.ts';

const FULL = { slug: 'reach-edu', display_name: 'Reach Edu', bucket: 'reach-edu' };

test('HEADER-06 the trigger degrades to the name we have, never to nothing', () => {
  assert.equal(workspaceLabel(FULL, 'Reach Edu'), 'Reach Edu');

  // The reported case: a client holding a payload older than the `workspace`
  // field. `label` has been sent all along, so it is what shows.
  assert.equal(workspaceLabel(null, 'Reach Edu'), 'Reach Edu');

  // Only with nothing at all does the placeholder appear.
  assert.equal(workspaceLabel(null, ''), '—');
  assert.equal(workspaceLabel({ ...FULL, display_name: '' }, 'from-label'), 'from-label');
});

test('HEADER-06 storage is stated only when known', () => {
  assert.equal(workspaceStorage(FULL), 'bucket reach-edu');
  assert.equal(workspaceStorage({ ...FULL, bucket: '' }), 'local folder');

  // Absent is NOT local. Saying "local folder" because a field was missing is a
  // confident wrong answer about where someone's corpus lives.
  assert.equal(workspaceStorage(null), '');
});
