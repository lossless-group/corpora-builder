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
const ramps = {};
for (const [, name, step, hex] of css.matchAll(/--color__([a-z]+)-(\d+):\s*(#[0-9a-f]{6})/g))
  (ramps[name] ??= []).push([Number(step), hex]);
for (const [name, steps] of Object.entries(ramps)) {
  steps.sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < steps.length; i++)
    if (lum(steps[i][1]) >= lum(steps[i - 1][1]))
      fails.push(`D3 --color__${name}-${steps[i][0]} is not darker than -${steps[i - 1][0]}`);
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
  [...css.matchAll(/--color-[a-z0-9-]+:[^;]*var\(--color__([a-z]+-\d+)\)/g)].map((m) => m[1]),
);
for (const [name, steps] of Object.entries(ramps))
  for (const [step, hex] of steps) {
    if (!inUse.has(`${name}-${step}`)) continue;
    const m = design.match(new RegExp(`^\\s+${name}-${step}:\\s*"(#[0-9a-f]{6})"`, 'm'));
    if (!m) fails.push(`D4 DESIGN.md is missing ${name}-${step}, which Tier 2 points at`);
    else if (m[1] !== hex) fails.push(`D4 ${name}-${step}: DESIGN.md says ${m[1]}, tokens.css says ${hex}`);
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
