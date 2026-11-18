// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 João Harrison
//
// Budget check - the three answers, in plain JS. This is a line-for-line mirror of
// src/mediekjop/planner/budget_check.py (Python is the source of truth); parity is
// pinned by golden cases in tests/test_budget_check_parity.py. The bands and
// constants come from budget-data.js, generated from config/planner/formats.yaml,
// so neither side hand-copies the numbers. Runs in the browser (window.HMCore) and
// in Node (module.exports) with no DOM.
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory(require('./budget-data.js'), require('./budget-ai-data.js'));
  } else {
    root.HMCore = factory(root.HM_DATA, root.HM_AI);
  }
})(typeof self !== 'undefined' ? self : this, function (DATA, AI) {
  var INDUSTRIES = DATA.industries, FORMATS = DATA.formats;
  var TYP_LO = DATA.typ_lo, TYP_HI = DATA.typ_hi, DEFAULT_CPM = DATA.default_cpm;

  // --- helpers (must match budget_check.py exactly) ---
  function hround(x) { return Math.floor(x + 0.5); }   // half up, like Python _round
  function sig2(x) {                                     // 2 significant figures (rough estimates)
    x = Number(x); if (x === 0) return 0;
    var neg = x < 0, ax = Math.abs(x);
    var digits = ax >= 1 ? String(Math.floor(ax)).length : 1;
    var factor = Math.pow(10, digits - 2);
    var val = hround(ax / factor) * factor;
    return neg ? -val : val;
  }
  function kr(n) {
    n = hround(n);
    var neg = n < 0, s = Math.abs(n).toString(), out = '';
    for (var i = 0; i < s.length; i++) {
      if (i > 0 && (s.length - i) % 3 === 0) out += ' ';
      out += s[i];
    }
    return (neg ? '-' : '') + out;
  }
  function num(v) {
    if (v == null) return 0;
    var n = parseFloat(String(v).replace(/\s/g, '').trim() || '0');
    return isFinite(n) ? n : 0;
  }
  function industry(key) {
    for (var i = 0; i < INDUSTRIES.length; i++) if (INDUSTRIES[i].key === key) return INDUSTRIES[i];
    return INDUSTRIES[0];
  }
  function format(key) {
    for (var i = 0; i < FORMATS.length; i++) if (FORMATS[i].key === key) return FORMATS[i];
    return FORMATS[2];
  }
  function isBlank(v) { return v == null || String(v).trim() === '' || num(v) <= 0; }

  function nouns(inp, ind) {
    if (ind.free_noun) {
      var base = (inp.otherNoun != null && String(inp.otherNoun).trim() !== '' ? String(inp.otherNoun).trim() : '') || ind.one;
      return [base, base + 's'];
    }
    return [ind.one, ind.many];
  }
  function valuePer(price, inp) {
    var m = num(inp.margin);
    if (inp.margin != null && String(inp.margin).trim() !== '' && m > 0) {
      return [(inp.marginUnit === 'kr' ? m : price * m / 100), true];
    }
    return [price, false];
  }
  function whoTypical(who) { return 'a typical ' + (who.indexOf('The ') === 0 ? who.slice(4) : who.toLowerCase()); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function blankNote(hb, ab, fmt) {
    var h = fmt.human, a = fmt.ai;
    if (hb && ab) {
      return 'Typical ranges — human ' + kr(h.low) + '–' + kr(h.high) + ' kr, AI ' +
        kr(a.low) + '–' + kr(a.high) + ' kr. Put in your quotes for a sharper answer.';
    }
    if (hb) {
      return 'Typical range: ' + kr(h.low) + '–' + kr(h.high) + ' kr. Put in your quote for a sharper answer.';
    }
    if (ab) {
      return 'Typical AI cost: ' + kr(a.low) + '–' + kr(a.high) + ' kr. Put in your figure for a sharper answer.';
    }
    return '';
  }

  function answerHumanMargin(human, ai, valPer, marginUsed, reuse, goal, reachable, one, many, fmt, hb, ab) {
    var diff = human - ai;
    var note = blankNote(hb, ab, fmt);
    var subject = cap(hb ? whoTypical(fmt.who) : fmt.who);
    var aiName = ab ? 'a typical AI version' : 'the AI version';
    var about = (hb || ab) ? 'about ' : '';
    if (valPer <= 0) {
      return { big: '—', unit: '', text: 'Add a value per ' + one + ' to see this.',
        has_context: false, context: '', how: '', note: note };
    }
    if (diff <= 0) {
      return {
        big: '0', unit: 'extra ' + many,
        text: subject + ' costs no more than ' + aiName + ', so it needs no extra ' + many + ' to pay for itself.',
        has_context: false, context: '',
        how: subject + ' ' + kr(human) + ' kr, ' + aiName + ' ' + kr(ai) +
          ' kr: no cost gap to cover.\nCosts count money paid out, not your own time.',
        note: note
      };
    }
    var extra = Math.ceil(diff / valPer);
    var per = Math.ceil(diff / (valPer * reuse));
    var share = reachable ? hround(per / goal * 100) : null;   // uses the displayed per-campaign figure
    var body = reuse > 1
      ? 'Across ' + reuse + ' campaigns, the human version needs ' + kr(extra) + ' more ' + many +
        ' than ' + aiName + ' to pay for itself, about ' + per + ' per campaign.'
      : 'The human version needs ' + kr(extra) + ' more ' + (extra === 1 ? one : many) +
        ' than ' + aiName + ' to pay for itself.';
    var context = '';
    if (share !== null) {
      context = 'That is ' + (share < 1 ? 'under 1' : share) + '% of your ' + kr(goal) + '-' + one +
        ' target per campaign. Whether a human version earns that is your call.';
    }
    var basis = marginUsed ? kr(valPer) + ' kr margin per ' + one : kr(valPer) + ' kr per ' + one;
    var marginLine = marginUsed ? 'Uses your margin per ' + one + '.\n'
      : 'Uses the full price. If you know your margin per ' + one + ', use that instead: the number goes up.\n';
    var how = kr(diff) + ' kr extra ÷ ' + basis + ' = ' + kr(extra) + ' ' + many + ' (rounded up).\n' +
      (reuse > 1 ? 'Spread over ' + reuse + ' campaigns: about ' + per + ' each.\n' : '') +
      marginLine +
      'A longer-term brand effect for human work is cited in research but kept out of this number (low confidence).';
    return {
      big: kr(extra), unit: 'more ' + (extra === 1 ? one : many),
      text: subject + ' costs ' + about + kr(diff) + ' kr more than ' + aiName + '. ' + body,
      has_context: share !== null, context: context, how: how, note: note
    };
  }

  function answerBudget(budget, cpm, goal, isTarget, views, oneIn, one, many) {
    if (budget <= 0 || cpm <= 0) {
      return { big: '—', text: 'Add a media budget to see this.', how: '' };
    }
    // CPM-derived estimates round to 2 significant figures; exact inputs and maths stay exact.
    var vd = kr(sig2(views));
    if (isTarget && goal > 0) {
      var maxCps = budget / goal;
      var pos = oneIn < TYP_LO ? 'well above what paid campaigns usually achieve'
        : (oneIn <= TYP_HI ? 'within what paid campaigns usually achieve'
          : 'comfortably inside what paid campaigns usually achieve');
      var oi = kr(sig2(oneIn));
      return {
        big: kr(maxCps) + ' kr per ' + one,
        text: 'To reach ' + kr(goal) + ' ' + many + ' on ' + kr(budget) + ' kr, each can cost at most ' +
          kr(maxCps) + ' kr. That means about 1 in ' + oi +
          ' ad views would need to become a ' + one + ': ' + pos + ' (usually 1 in ' + kr(TYP_LO) + '–' + kr(TYP_HI) + ').',
        how: 'Max cost per ' + one + ': ' + kr(budget) + ' kr ÷ ' + kr(goal) + ' = ' + kr(maxCps) + ' kr.\n' +
          'Views: ' + kr(budget) + ' kr at a ' + kr(cpm) + ' kr CPM ≈ ' + vd +
          ' (one person may see the ad more than once).\n' +
          'Needed: ' + kr(goal) + ' ' + many + ' from ' + vd + ' views ≈ 1 in ' + oi + '.\n' +
          'Usual range is a rough US-based estimate. Put in your own CPM under “I know my own numbers”.'
      };
    }
    var lo = Math.floor(views / TYP_HI), hi = Math.ceil(views / TYP_LO);
    var cpsLo = hi > 0 ? budget / hi : 0, cpsHi = lo > 0 ? budget / lo : 0;
    var lod = kr(sig2(lo)), hid = kr(sig2(hi));
    return {
      big: 'Usually ' + lod + '–' + hid + ' ' + many,
      text: 'At a typical CPM, ' + kr(budget) + ' kr covers about ' + vd +
        ' views. Paid campaigns usually turn 1 in ' + kr(TYP_LO) + '–' + kr(TYP_HI) +
        ' views into a ' + one + ', so roughly ' + lod + '–' + hid + ' ' + many +
        (lo > 0 ? ', at ' + kr(sig2(cpsLo)) + '–' + kr(sig2(cpsHi)) + ' kr each.' : '.'),
      how: 'Views: ' + kr(budget) + ' kr at a ' + kr(cpm) + ' kr CPM ≈ ' + vd + '.\n' +
        'Usual conversion: 1 in ' + kr(TYP_LO) + '–' + kr(TYP_HI) + ' views (rough US-based estimate).\n' +
        'Put in your own CPM under “I know my own numbers”.'
    };
  }

  function answerQuote(humanBlank, human, fmt) {
    var low = fmt.human.low, high = fmt.human.high, scaleMax = high * 1.3;
    var pct = function (x) { return scaleMax > 0 ? Math.max(0, Math.min(100, x / scaleMax * 100)) : 0; };
    var how = 'Usual range: owner-reviewed estimate for Oslo, November 2026. Money paid out, ' +
      'including usage rights for paid social.\nYour own quote always replaces the range in the other answers.';
    if (humanBlank) {
      return {
        big: 'Typical range',
        text: 'No quote entered — ' + fmt.noun + ' in Oslo usually runs ' +
          kr(low) + '–' + kr(high) + ' kr. Put in your quote to place it.',
        blank: true, low: low, high: high, human: human, scale_max: scaleMax,
        pct_low: pct(low), pct_high: pct(high), pct_human: pct(human), how: how
      };
    }
    var where = human < low ? 'below the usual range' : (human > high ? 'above the usual range' : 'inside the usual range');
    var big = human < low ? 'Below usual' : (human > high ? 'Above usual' : 'Inside usual range');
    return {
      big: big,
      text: kr(human) + ' kr for ' + fmt.noun + ' sits ' + where + ' in Oslo (' + kr(low) + '–' + kr(high) + ' kr).',
      blank: false, low: low, high: high, human: human, scale_max: scaleMax,
      pct_low: pct(low), pct_high: pct(high), pct_human: pct(human), how: how
    };
  }

  function compute(inp) {
    var ind = industry(inp.industry), fmt = format(inp.fmt);
    var nm = nouns(inp, ind), one = nm[0], many = nm[1];
    var price = num(inp.price), goal = num(inp.goal), budget = num(inp.budget);
    var reuse = Math.max(1, hround(num(inp.reuse)) || 1), cpm = num(inp.cpm);
    var isTarget = inp.goalMode === 'target';
    var vp = valuePer(price, inp), valPer = vp[0], marginUsed = vp[1];

    var humanBlank = isBlank(inp.human), aiBlank = isBlank(inp.ai);
    var human = humanBlank ? fmt.human.point : num(inp.human);
    var ai = aiBlank ? fmt.ai.point : num(inp.ai);

    var views = cpm > 0 ? budget / cpm * 1000 : 0;
    var oneIn = (isTarget && goal > 0 && views > 0) ? hround(views / goal) : null;
    var reachable = oneIn !== null && oneIn >= TYP_LO;

    return {
      unit_one: one, unit_many: many, human_eff: human, ai_eff: ai,
      value_per: valPer, margin_used: marginUsed,
      human_blank: humanBlank, ai_blank: aiBlank, reachable: reachable,
      a1: answerBudget(budget, cpm, goal, isTarget, views, oneIn, one, many),
      a2: answerHumanMargin(human, ai, valPer, marginUsed, reuse, goal, reachable, one, many, fmt, humanBlank, aiBlank),
      a3: answerQuote(humanBlank, human, fmt)
    };
  }

  // --- "If you go AI" tool options (mirrors budget_check.ai_options) ---
  var RULE_LABEL = { retouch_label: 'retouch label', misleading: 'misleading marketing', ai_act: 'EU AI Act' };
  var VOICE_FORMATS = { video: 1, ugc: 1 };
  var BADGE = { confirmed: 'Norwegian: confirmed', likely: 'Norwegian: likely', unverified: 'Norwegian: not confirmed' };
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function checkedDisplay(iso) {
    var p = String(iso).split('-');
    return parseInt(p[2], 10) + ' ' + MONTHS[parseInt(p[1], 10) - 1] + ' ' + parseInt(p[0], 10);
  }
  function toolView(t, aiCost, rulesById) {
    return {
      name: t.name, price_nok: t.price_nok, price_text: 'about ' + kr(t.price_nok) + ' kr/month',
      includes: t.includes || '', badge: BADGE[t.norwegian] || null, jurisdiction: t.jurisdiction || '',
      billing_note: t.billing_note || '', pros: (t.pros || []).slice(), cons: (t.cons || []).slice(),
      rules: (t.rules || []).map(function (r) {
        return { id: r, label: RULE_LABEL[r] || r, text: (rulesById[r] || {}).text || '',
          source: (rulesById[r] || {}).source || '' }; }),
      fits: aiCost > 0 && t.price_nok <= aiCost, source: t.source || ''
    };
  }
  function aiOptions(fmt, aiCost, todayISO) {
    var data = AI, ucs = {}, i;
    for (i = 0; i < data.use_cases.length; i++) ucs[data.use_cases[i].key] = data.use_cases[i];
    var fmtLabel = fmt;
    for (i = 0; i < FORMATS.length; i++) if (FORMATS[i].key === fmt) fmtLabel = FORMATS[i].label;

    var rulesById = {};
    (data.norway_rules || []).forEach(function (r) { rulesById[r.id] = r; });
    var main = null;
    for (i = 0; i < data.use_cases.length; i++) {
      var uc = data.use_cases[i];
      if (uc.key !== 'voice' && (uc.format_keys || []).indexOf(fmt) !== -1) { main = uc; break; }
    }
    var tools = (main ? main.tools : []).map(function (t) { return toolView(t, aiCost, rulesById); });
    var voice = null;
    if (VOICE_FORMATS[fmt] && ucs.voice) {
      voice = { label: ucs.voice.label, tools: ucs.voice.tools.map(function (t) { return toolView(t, aiCost, rulesById); }) };
    }
    var fb = data.free_baseline || {};
    var alts = (main && main.alternatives ? main.alternatives : []).map(function (a) {
      return { name: a.name, price_text: 'about ' + kr(a.price_nok) + ' kr/month', note: a.note || '', source: a.source || '' };
    });
    return {
      format: fmt, format_label: fmtLabel, use_case_label: main ? main.label : '',
      card_note: (main && main.card_note) || '',
      free_baseline: { name: fb.name || '', price: fb.price || '', note: fb.note || '', source: fb.source || '' },
      tools: tools, voice: voice, alternatives: alts,
      checked_display: data.checked ? checkedDisplay(data.checked) : '',
      review_by: data.review_by || '',
      stale: !!data.review_by && String(todayISO) > data.review_by
    };
  }

  // --- URL round-trip (numbers travel in the link; nothing is stored) ---
  var FIELDS = ['industry', 'goalMode', 'goal', 'price', 'budget', 'fmt', 'human', 'ai',
    'reuse', 'cpm', 'margin', 'marginUnit', 'otherNoun'];
  var _NULLABLE = { human: 1, ai: 1, margin: 1, otherNoun: 1 };   // empty -> null, not ''
  function toQuery(inp) {
    var q = new URLSearchParams();
    FIELDS.forEach(function (k) { q.set(k, inp[k] == null ? '' : inp[k]); });
    return q.toString();
  }
  function fromQuery(search) {
    var q = new URLSearchParams(search), out = {};
    FIELDS.forEach(function (k) {
      if (q.has(k)) {
        var v = q.get(k);
        out[k] = (_NULLABLE[k] && v === '') ? null : v;
      }
    });
    return out;
  }

  return { compute: compute, aiOptions: aiOptions, kr: kr, num: num, toQuery: toQuery,
    fromQuery: fromQuery, FIELDS: FIELDS, INDUSTRIES: INDUSTRIES, FORMATS: FORMATS,
    TYP_LO: TYP_LO, TYP_HI: TYP_HI, DEFAULT_CPM: DEFAULT_CPM };
});
