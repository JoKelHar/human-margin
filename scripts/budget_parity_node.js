// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 João Harrison
//
// JS/Python parity + URL round-trip check for the budget calculator. Loads the
// plain-JS core and the golden cases generated from Python, and asserts that the JS
// reproduces every golden output exactly, and that encoding inputs to the URL and
// back yields the same answers. Exits non-zero on any mismatch (run by
// tests/test_budget_check_parity.py).
//
//     node scripts/budget_parity_node.js
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const core = require(path.join(ROOT, 'web', 'budget-core.js'));
const golden = require(path.join(ROOT, 'tests', 'golden', 'budget_check.json'));

function sort(o) {
  if (Array.isArray(o)) return o.map(sort);
  if (o && typeof o === 'object') {
    const r = {};
    for (const k of Object.keys(o).sort()) r[k] = sort(o[k]);
    return r;
  }
  return o;
}
function eq(a, b) { return JSON.stringify(sort(a)) === JSON.stringify(sort(b)); }

let parityFails = 0, roundtripFails = 0;
const show = [];
for (const c of golden) {
  const got = core.compute(c.input);
  if (!eq(got, c.output)) {
    parityFails++;
    if (show.length < 3) {
      for (const k of ['a1', 'a2', 'a3']) {
        if (!eq(got[k], c.output[k])) {
          show.push('PARITY ' + k + ' input=' + JSON.stringify(c.input) +
            '\n  JS=' + JSON.stringify(got[k]) + '\n  PY=' + JSON.stringify(c.output[k]));
        }
      }
    }
  }
  // URL round-trip: encode -> decode -> same answers.
  const back = core.fromQuery('?' + core.toQuery(c.input));
  if (!eq(core.compute(back), core.compute(c.input))) {
    roundtripFails++;
    if (show.length < 3) show.push('ROUNDTRIP input=' + JSON.stringify(c.input));
  }
}

if (parityFails || roundtripFails) {
  console.error(show.join('\n'));
  console.error('FAIL: ' + parityFails + ' parity, ' + roundtripFails + ' round-trip, of ' + golden.length);
  process.exit(1);
}
console.log('OK: ' + golden.length + ' cases - JS matches Python golden, URL round-trip stable.');
