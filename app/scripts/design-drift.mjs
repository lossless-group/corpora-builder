#!/usr/bin/env node
/**
 * Design drift check — makes the three rules in `tokens.css` checkable.
 *
 * Named after and modelled on `augment-it/scripts/design-drift.mjs`, which
 * exists because that system spent five revisions with F1–F11 as prose and
 * discovered, the day they became checks, that three members were reading a
 * Tier-1 name directly. A rule nothing runs is a preference.
 *
 * Zero dependencies. Exits non-zero on any violation.
 *
 *   D1  no component reads a Tier-1 name       (`var(--color__…)` outside tokens.css)
 *   D2  no colour literal outside Tier 1       (a colour with no name)
 *   D3  step numbers track darkness            (a name that lies; augment-it's A19)
 *   D4  DESIGN.md and tokens.css agree on every Tier-1 hex
 *   D5  no component reads a token that does not exist
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = new URL('..', import.meta.url).pathname;
const TOKENS = join(ROOT, 'src/lib/styles/tokens.css');
const DESIGN = join(ROOT, 'DESIGN.md');
const css = readFileSync(TOKENS, 'utf8');
const fails = [];

const walk = (dir) =>
  readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
const components = walk(join(ROOT, 'src')).filter(
  (p) => /\.(svelte|css|ts)$/.test(p) && p !== TOKENS,
);

// D1 — Tier 1 is written once and read by nothing but Tier 2.
for (const file of components) {
  const src = readFileSync(file, 'utf8');
  src.split('\n').forEach((line, i) => {
    if (line.includes('var(--color__'))
      fails.push(`D1 ${relative(ROOT, file)}:${i + 1} reads a Tier-1 name — use a semantic token`);
  });
}

// D2 — below the Tier-1 block, a colour literal is a colour with no name.
// Anchor on the section banner, not on the string "Tier 2" — the file's own
// header comment explains the tiers, and slicing there made every primitive
// look like a violation the first time this ran.
const tier2At = css.indexOf('Tier 2: semantic');
const offset = css.slice(0, tier2At).split('\n').length;
css.slice(tier2At).split('\n').forEach((line, i) => {
  if (/#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d/.test(line) && !line.trimStart().startsWith('*'))
    fails.push(`D2 tokens.css:${offset + i} colour literal below Tier 1 — give it a name`);
});
for (const file of components) {
  const src = readFileSync(file, 'utf8');
  src.split('\n').forEach((line, i) => {
    if (/#[0-9a-fA-F]{6}\b|rgba?\(\s*\d/.test(line) && /(color|background|border|shadow|fill|stroke)/i.test(line))
      fails.push(`D2 ${relative(ROOT, file)}:${i + 1}: colour literal in a component`);
  });
}

// D3 — an agent reasons from `navy-900 is darker than navy-700`. It must be true.
const lum = (hex) => {
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(1 + i, 3 + i), 16) / 255);
  const f = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
// Two inversions inherited verbatim from augment-it's palette, kept rather than
// silently renumbered so the Tier-1 vocabulary stays byte-identical across the
// two repos. Both are the class augment-it named A19 and declared resolved after
// renumbering graphite and mist; paper and void still lie:
//
//   paper-200 #f4f2ec is lighter than paper-100 #f1efe9   (swapped)
//   void-700  #16101f is darker  than void-900  #1c1429   (misplaced; it should
//                                                          sort below 850)
//
// Listed, not suppressed: an exception with a reason is reviewable, a check
// quietly relaxed is not. Delete these two lines when upstream renumbers.
const KNOWN_UPSTREAM = new Set(['paper-200', 'void-800']);

// Every named colour, for D4. `ramps` is the numeric subset, for D3 — an
// earlier version built only `ramps` and therefore never checked the accents,
// which are the colours a reader of DESIGN.md most needs to be right.
const tier1 = Object.fromEntries(
  [...css.matchAll(/--color__([a-z]+-[a-z0-9]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1], m[2]]),
);
const ramps = {};
for (const [, name, step, hex] of css.matchAll(/--color__([a-z]+)-(\d+):\s*(#[0-9a-f]{6})/g))
  (ramps[name] ??= []).push([Number(step), hex]);
for (const [name, steps] of Object.entries(ramps)) {
  steps.sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < steps.length; i++)
    if (lum(steps[i][1]) > lum(steps[i - 1][1]) && !KNOWN_UPSTREAM.has(`${name}-${steps[i][0]}`))
      fails.push(`D3 --color__${name}-${steps[i][0]} is LIGHTER than -${steps[i - 1][0]}`);
}

// D5 — a var() naming nothing paints nothing, silently. augment-it counted 33
// of these; they are invisible in review because the CSS is syntactically fine.
const defined = new Set([...css.matchAll(/^\s*(--[a-z0-9_-]+):/gm)].map((m) => m[1]));
for (const file of components) {
  const src = readFileSync(file, 'utf8');
  src.split('\n').forEach((line, i) => {
    for (const [, tok] of line.matchAll(/var\((--[a-z0-9_-]+)/g))
      if (!defined.has(tok))
        fails.push(`D5 ${relative(ROOT, file)}:${i + 1} reads ${tok}, which is not declared`);
  });
}

// D4 — the document is the contract, and nothing else compares it to the
// runtime. augment-it shipped a DESIGN.md quoting a hex its theme had already
// changed, so an agent reading the document got the wrong colour.
//
// Scope is every Tier-1 colour a Tier-2 token actually points at. The unused
// ramp steps are inventory, not contract, and demanding all 34 would make the
// document longer without making it truer.
const design = readFileSync(DESIGN, 'utf8');
const inUse = new Set(
  [...css.matchAll(/--(?:color|fx)-[a-z0-9-]+:[^;]*var\(--color__([a-z]+-[a-z0-9]+)\)/g)].map((m) => m[1]),
);
for (const name of [...inUse].sort()) {
  const hex = tier1[name];
  const m = design.match(new RegExp(`^\\s+${name}:\\s*"(#[0-9a-f]{6})"`, 'm'));
  if (!m) fails.push(`D4 DESIGN.md is missing ${name}, which Tier 2 points at`);
  else if (m[1] !== hex) fails.push(`D4 ${name}: DESIGN.md says ${m[1]}, tokens.css says ${hex}`);
}

if (fails.length) {
  console.error(fails.map((f) => `  ${f}`).join('\n'));
  console.error(`\n  ${fails.length} design-drift violation(s)`);
  process.exit(1);
}
console.log(
  `  design: clean — ${components.length} files, ${Object.keys(ramps).length} ramps ` +
    `(${Object.values(ramps).flat().length} colours), ${inUse.size} in use and ` +
    `verified against DESIGN.md`,
);
