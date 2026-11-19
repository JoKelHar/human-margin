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
const aiGolden = require(path.join(ROOT, 'tests', 'golden', 'ai_options.json'));
const creatorGolden = require(path.join(ROOT, 'tests', 'golden', 'creator.json'));

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

let aiFails = 0;
for (const c of aiGolden) {
  const got = core.aiOptions(c.input.fmt, c.input.ai_cost, c.input.today);
  if (!eq(got, c.output)) {
    aiFails++;
    if (show.length < 3) show.push('AI ' + JSON.stringify(c.input) +
      '\n  JS=' + JSON.stringify(got).slice(0, 200) + '\n  PY=' + JSON.stringify(c.output).slice(0, 200));
  }
}

let creatorFails = 0, creatorRtFails = 0;
for (const c of creatorGolden) {
  const got = core.creatorCompute(c.input);
  if (!eq(got, c.output)) {
    creatorFails++;
    if (show.length < 3) show.push('CREATOR ' + JSON.stringify(c.input) +
      '\n  JS=' + JSON.stringify(got).slice(0, 220) + '\n  PY=' + JSON.stringify(c.output).slice(0, 220));
  }
  const back = core.fromQuery('?' + core.toQuery(c.input));
  if (!eq(core.creatorCompute(back), core.creatorCompute(c.input))) {
    creatorRtFails++;
    if (show.length < 3) show.push('CREATOR ROUNDTRIP ' + JSON.stringify(c.input));
  }
}

// mailto encoding: fields are URL-encoded into the mailto body/subject.
let mailFails = 0;
const mt = core.creatorMailto({ fmt: 'ugc', price: 3500, usageMonths: 6, revisions: 2, rawFiles: true },
  'hello@human-margin.example');
if (mt.indexOf('mailto:hello@human-margin.example?subject=') !== 0 ||
    decodeURIComponent(mt.split('subject=')[1].split('&')[0]).indexOf('Range feedback') === -1 ||
    decodeURIComponent(mt.split('&body=')[1]).indexOf('My price: 3 500 kr') === -1 ||
    decodeURIComponent(mt.split('&body=')[1]).indexOf('Raw files: yes') === -1 ||
    mt.indexOf(' ') !== -1) {   // a real mailto has no raw spaces
  mailFails++; show.push('MAILTO bad: ' + mt);
}
creatorRtFails += mailFails;

if (parityFails || roundtripFails || aiFails || creatorFails || creatorRtFails) {
  console.error(show.join('\n'));
  console.error('FAIL: ' + parityFails + ' parity, ' + roundtripFails + ' round-trip, ' +
    aiFails + ' ai-options, ' + creatorFails + ' creator, ' + creatorRtFails + ' creator-rt/mailto, of ' +
    golden.length + '/' + aiGolden.length + '/' + creatorGolden.length);
  process.exit(1);
}
console.log('OK: ' + golden.length + ' answer + ' + aiGolden.length + ' ai-options + ' +
  creatorGolden.length + ' creator cases - JS matches Python golden, URL round-trip stable.');
