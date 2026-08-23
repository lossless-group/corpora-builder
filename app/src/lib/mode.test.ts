/** Covers `context-v/specs/Header-Chrome.md` — the toggle's own rules. */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MODES, modeTooltip, nextMode, type Mode } from './modes.ts';

test('HEADER-04 the cycle is light → dark → vibrant → light', () => {
  assert.equal(nextMode('light'), 'dark');
  assert.equal(nextMode('dark'), 'vibrant');
  assert.equal(nextMode('vibrant'), 'light');

  // Every mode is reachable from every mode — a cycle, not a dead end.
  let m: Mode = MODES[0];
  const seen = new Set<Mode>([m]);
  for (let i = 0; i < MODES.length; i++) seen.add((m = nextMode(m)));
  assert.equal(seen.size, MODES.length);
  assert.equal(m, MODES[0], 'the cycle must close');
});

test('HEADER-05 the tooltip names this mode and the next, and cannot disagree', () => {
  assert.equal(modeTooltip('dark'), 'Dark mode · click for Vibrant');
  assert.equal(modeTooltip('light'), 'Light mode · click for Dark');
  assert.equal(modeTooltip('vibrant'), 'Vibrant mode · click for Light');

  // Derived, not written out: whatever the cycle says, the tooltip says. This is
  // the assertion that survives someone reordering MODES.
  for (const m of MODES) {
    const t = modeTooltip(m);
    assert.ok(t.toLowerCase().startsWith(m), `"${t}" must open with the current mode`);
    assert.ok(
      t.toLowerCase().endsWith(nextMode(m)),
      `"${t}" must end with ${nextMode(m)}, the mode a click produces`,
    );
  }
});
