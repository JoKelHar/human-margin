# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Creative Approach Planner - decision engine.

Turns a validated :class:`~mediekjop.planner.schema.Scenario` into a *position*
on the AI-vs-hybrid-vs-human trade-off, backed by cited benchmarks and honest
uncertainty. It never picks for the user: it reports which approach delivers the
most conversions per krone on these inputs, the break-even response lift the
higher-cost approach would need to match, a separate (not-in-funnel) brand line,
and which inputs the answer hinges on. Copy lives in :mod:`report`; this module
only computes.

The model, per (approach, format) cell::

    impressions  = budget / cpm * 1000
    ctr          = base_ctr * format.ctr_mult * response_mult[approach]
    cvr          = base_cvr * format.cvr_mult
    conversions  = impressions * ctr * cvr
    value        = conversions * value_per_conversion
    production   = cost[format, approach] / reuse_campaigns
    net_margin   = value - budget - production

``response_mult`` is the cited AI-vs-human *response* prior (centred at parity),
applied to CTR only where it was measured; it is 1.0 for human_led, the sampled
prior for ai_generated, and the midpoint for ai_assisted. The *memory_brand*
prior is deliberately kept OUT of the funnel and surfaced as a separate line.

Uncertainty is propagated by sampling each input from a triangular
``(low, point, high)`` distribution with a fixed seed, and reporting p10/p50/p90
- never by multiplying lows and highs together.

Break-even (headline), human_led vs ai_generated at one shared format::

    lift = (prod_human - prod_ai) / (reuse * value_per_conv * conversions_ai)

i.e. the fraction by which human-led's response must exceed ai_generated's to
match on margin. It falls straight out of the margin-match condition and does not
depend on the AI response draw itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import benchmarks as bm
from .currency import SUPPORTED, FxRates, Money, load_fx_rates
from .formats import Format, Tri, baseline_format, load_costs, load_formats
from .schema import Scenario

APPROACHES = ("human_led", "ai_assisted", "ai_generated")
APPROACH_LABEL = {
    "human_led": "human-led",
    "ai_assisted": "hybrid (AI-assisted)",
    "ai_generated": "AI-generated",
}
DEFAULT_SEED = 20260101
DEFAULT_DRAWS = 5000
OVERRIDE_SPREAD = 0.15          # ±band around a supplied cost (so it can swing)


# --- helpers ----------------------------------------------------------------

def _rate_to_fraction(value: float, unit: str | None) -> float:
    """A rate stored as a percent ('percent' unit) -> fraction; by UNIT, not magnitude.

    A CTR of 0.84% has value 0.84 (< 1) but is still a percent; a magnitude test
    would wrongly read it as the fraction 0.84. The unit is authoritative.
    """
    return float(value) / 100.0 if (unit or "").lower() in ("percent", "pct", "%") else float(value)


def _tri_from_estimate(est: bm.Estimate, rate: bool = False) -> Tri:
    f = (lambda v: _rate_to_fraction(v, est.unit)) if rate else (lambda v: float(v))
    lo, pt, hi = f(est.low), f(est.point), f(est.high)
    lo, hi = min(lo, pt), max(hi, pt)
    return Tri(lo, pt, hi)


def _cpm_tri_nok(est: bm.Estimate, fx: FxRates) -> Tri:
    """CPM benchmarks are stored in their source currency; convert to NOK."""
    unit = (est.unit or "nok").upper()
    if unit in SUPPORTED and unit != "NOK":
        conv = lambda v: fx.to_nok(Money(float(v), unit))  # noqa: E731
    else:
        conv = lambda v: float(v)  # noqa: E731  (already NOK or unit-free)
    lo, pt, hi = conv(est.low), conv(est.point), conv(est.high)
    return Tri(min(lo, pt), pt, max(hi, pt))


def _draw(tri: Tri, n: int, rng: np.random.Generator) -> np.ndarray:
    if tri.low == tri.high:
        return np.full(n, tri.point)
    # numpy's triangular needs left <= mode <= right; guaranteed by Tri.
    return rng.triangular(tri.low, tri.point, tri.high, n)


def _pcts(a: np.ndarray) -> tuple[float, float, float]:
    p10, p50, p90 = np.percentile(a, [10, 50, 90])
    return float(p10), float(p50), float(p90)


def _perf_prior(effect: str, rows: list[dict]) -> tuple[Tri, bm.Estimate | None]:
    """The cited human-vs-AI performance prior for one effect, as a range + tag."""
    matches = [e for e in rows if e["metric"] == "perf_multiplier" and e.get("effect") == effect]
    if not matches:
        return Tri(1.0, 1.0, 1.0), None
    e = matches[0]
    v = e["value"]
    tri = Tri(float(v.get("low", v["point"])), float(v["point"]), float(v.get("high", v["point"])))
    # Wrap the single row in an Estimate so the report can tag it consistently.
    est = bm.Estimate(
        metric="perf_multiplier", low=tri.low, point=tri.point, high=tri.high,
        unit=e["unit"], markets=[e["geography"]], source_quality=e["quality"],
        relevance="low", relevance_reasons=["geography: global prior, not Norway"],
        confidence="low", provenance=bm.provenance(e), primary_market=e["geography"],
        year=e["published"].year if hasattr(e["published"], "year") else None,
        n_sources=1, any_stale=bm.is_stale(e),
    )
    return tri, est


# --- result types -----------------------------------------------------------

@dataclass
class MetricUse:
    """A benchmark estimate the plan leaned on, for the evidence section."""
    name: str
    est: bm.Estimate | None
    tag: str


@dataclass
class Cell:
    approach: str
    fmt: str
    conv: tuple[float, float, float]        # p10/p50/p90 conversions
    margin: tuple[float, float, float]      # p10/p50/p90 net margin (NOK)
    conv_per_1000: float                    # p50 conversions per 1000 kr all-in
    cost_per_conv: float                    # p50 NOK per conversion (media+prod)
    prod_tier: str
    prod_filled: bool


@dataclass
class BreakEven:
    fmt: str
    lift: tuple[float, float, float]        # p10/p50/p90 required response lift (fraction)
    prod_human: float                       # p50 amortised production, human_led
    prod_ai: float                          # p50 amortised production, ai_generated
    conv_ai: float                          # p50 ai_generated conversions
    feasible: bool                          # both approaches can make this format


@dataclass
class BreakEvenCost:
    """Headline break-even expressed as a PRODUCTION COST (the natural lever): the
    human-led production cost at which human-led matches the best AI option on
    margin, p10/p50/p90 - funnel only, and again with the human brand effect added
    (which raises it). A supplied quote is placed against the two, position only."""
    fmt: str
    funnel: tuple[float, float, float]        # p10/p50/p90 NOK, funnel only
    with_brand: tuple[float, float, float]    # p10/p50/p90 NOK, incl. brand effect
    feasible: bool                            # human_led can make the headline format
    ai_label: str = ""                        # the one AI comparator, named (AI's strongest option)
    # The scenario's OWN human-led cost at the headline format, placed automatically.
    own_cost_nok: float | None = None
    own_placement: str | None = None          # above_both | between | below_both
    # An optional override quote (human_quote / --quote) to test another figure.
    quote_nok: float | None = None
    placement: str | None = None              # above_both | between | below_both


@dataclass
class BrandLine:
    fmt: str
    funnel_gap: float                       # p50 (ai_margin - human_margin); >0 = AI ahead on funnel
    brand_value: float                      # p50 modelled human long-term brand value (separate)
    worth_to_close: float                   # p50 kr the brand effect must be worth to close the gap
    mb_tier: str
    mb_tag: str
    ai_label: str = ""                      # the one AI comparator, named (AI's strongest option)


@dataclass
class Sensitivity:
    driver: str                             # human-readable input name
    swing: float                            # how much it moves the headline (fraction of range)


@dataclass
class RoasCheck:
    implied: float                          # p50 funnel-implied ROAS for the leading cell
    benchmark: float | None                 # benchmark roas point, if any
    note: str


@dataclass
class PlanResult:
    scenario: Scenario
    headline_format: str
    leader: str                             # approach with most conversions per krone (p50)
    cells: list[Cell]
    breakeven: BreakEven
    breakeven_cost: BreakEvenCost
    brand: BrandLine
    sensitivity: list[Sensitivity]
    roas: RoasCheck
    metrics: list[MetricUse]
    confidence: str                         # overall, from the estimates leaned on
    capacity_capped: bool
    draws: int
    seed: int
    # Sanity flags (the product's core job: say plainly when the economics don't work).
    reach_p50: float = 0.0                  # best uncapped conversions the budget buys (p50)
    over_value: list[str] = field(default_factory=list)  # approaches whose cheapest sale
                                            # still costs more than one conversion is worth
    level: bool = False                     # leading approaches are within ~5% -> no single leader
    level_pair: list[str] = field(default_factory=list)  # the two approaches that are level
    channel: str = "meta"
    notes: list[str] = field(default_factory=list)


# --- the engine -------------------------------------------------------------

def _response_mult(approach: str, resp_draw: np.ndarray) -> np.ndarray:
    if approach == "human_led":
        return np.ones_like(resp_draw)
    if approach == "ai_generated":
        return resp_draw
    return (1.0 + resp_draw) / 2.0          # hybrid: partway between human and AI


def _mb_mult(approach: str, mb_draw: np.ndarray) -> np.ndarray:
    # memory_brand is the HUMAN long-term edge; AI = 1.0, hybrid partway.
    if approach == "human_led":
        return mb_draw
    if approach == "ai_generated":
        return np.ones_like(mb_draw)
    return (1.0 + mb_draw) / 2.0


def _headline_format(scn: Scenario, formats: dict[str, Format]) -> str:
    """The scenario's chosen format, or a sensible shared one for the comparison.

    Precedence: an explicit content_format (e.g. CLI --format) wins; otherwise the
    scenario's ``costs.format`` drives the headline, so the position, break-even,
    cost-per-sale, brand effect and sensitivity all run on the one format the
    advertiser priced (and the supplied human cost for it is placed automatically).
    Only when neither is given does the engine auto-pick a shared comparison format."""
    chosen = getattr(scn, "content_format", None)
    if chosen and chosen in formats:
        return chosen
    cf = scn.costs.format
    if cf and cf in formats:
        return cf
    # Prefer a format both human_led and ai_generated can produce; favour short_video.
    both = [k for k, f in formats.items()
            if "human_led" in f.approaches and "ai_generated" in f.approaches]
    for pref in ("short_video", baseline_format()):
        if pref in both:
            return pref
    return both[0] if both else next(iter(formats))


def plan(scn: Scenario, *, benchmarks: list[dict] | None = None, weights: dict | None = None,
         fx: FxRates | None = None, draws: int = DEFAULT_DRAWS, seed: int = DEFAULT_SEED) -> PlanResult:
    """Run the decision engine on one validated scenario."""
    rows = benchmarks if benchmarks is not None else bm.load_benchmarks()
    wcfg = weights if weights is not None else bm.load_weights()
    fx = fx or load_fx_rates()
    formats = load_formats()
    costs = load_costs()
    rng = np.random.default_rng(seed)

    ind, band, chan = scn.industry, scn.band, scn.channel
    cpm_e = bm.estimate("cpm", ind, chan, band, benchmarks=rows, weights=wcfg)
    ctr_e = bm.estimate("ctr", ind, chan, band, benchmarks=rows, weights=wcfg)
    cvr_e = bm.estimate("cvr", ind, chan, band, benchmarks=rows, weights=wcfg)
    roas_e = bm.estimate("roas", ind, chan, band, benchmarks=rows, weights=wcfg)
    if not (cpm_e and ctr_e and cvr_e):
        raise bm.BenchmarkError("missing a core funnel benchmark (cpm/ctr/cvr)")

    resp_tri, resp_est = _perf_prior("response", rows)
    mb_tri, mb_est = _perf_prior("memory_brand", rows)

    # Shared funnel draws (same market conditions for every approach/format).
    cpm_tri = _cpm_tri_nok(cpm_e, fx)
    cpm = _draw(cpm_tri, draws, rng)
    base_ctr = _draw(_tri_from_estimate(ctr_e, rate=True), draws, rng)
    base_cvr = _draw(_tri_from_estimate(cvr_e, rate=True), draws, rng)
    resp = _draw(resp_tri, draws, rng)
    mb = _draw(mb_tri, draws, rng)
    impressions = scn.budget_nok / np.maximum(cpm, 1e-9) * 1000.0
    V = scn.value_per_conversion_nok
    R = max(scn.reuse_campaigns, 1)

    # Per-format multiplier draws (shared across approaches for that format).
    fmt_ctr = {k: _draw(f.ctr_mult, draws, rng) for k, f in formats.items()}
    fmt_cvr = {k: _draw(f.cvr_mult, draws, rng) for k, f in formats.items()}

    # Headline format and the one format a supplied cost prices (others use the library).
    hf = _headline_format(scn, formats)
    ov_fmt = _override_format(scn, formats, hf)

    def _conversions(approach: str, fkey: str) -> np.ndarray:
        rm = _response_mult(approach, resp)
        ctr = base_ctr * fmt_ctr[fkey] * rm
        cvr = base_cvr * fmt_cvr[fkey]
        return impressions * ctr * cvr

    def _prod(approach: str, fkey: str) -> np.ndarray:
        # A supplied cost overrides the library default for its one format only; every
        # other (format, approach) cell uses the formats.yaml band.
        ov = _override_tri(scn, approach, fkey, ov_fmt)
        if ov is not None:
            return _draw(ov, draws, rng) / R
        cell = costs.get((fkey, approach))
        if cell is None:
            return None  # type: ignore[return-value]
        return _draw(cell.nok, draws, rng) / R

    cells: list[Cell] = []
    reach_p50 = 0.0
    ai_options: list[dict] = []     # per-AI-cell arrays, to pick one shared comparator
    for fkey, f in formats.items():
        for approach in f.approaches:
            prod = _prod(approach, fkey)
            if prod is None:
                continue
            conv = _conversions(approach, fkey)
            reach_p50 = max(reach_p50, float(np.median(conv)))   # best uncapped volume
            # Capacity-capped: you cannot sell more than capacity, so value and the
            # headline metric saturate there and the objective becomes lowest cost
            # to reach it (cheapest sell-out), not most volume.
            conv_eff = np.minimum(conv, scn.capacity) if scn.is_capacity_capped() else conv
            margin = conv_eff * V - scn.budget_nok - prod
            if approach in ("ai_assisted", "ai_generated"):
                ai_options.append({"approach": approach, "fmt": fkey,
                                   "margin": margin, "conv": conv_eff})
            allin = scn.budget_nok + prod
            conv_per_1000 = conv_eff / np.maximum(allin, 1e-9) * 1000.0
            cost_per_conv = allin / np.maximum(conv_eff, 1e-9)
            cell = costs.get((fkey, approach))
            # If the advertiser supplied a cost for THIS format+approach, that is what
            # the cell used - their real figure, not a library draft.
            used_override = _override_amount(scn, approach, fkey, ov_fmt) is not None
            if used_override:
                prod_tier, prod_filled = "own_scenario", True
            else:
                prod_tier = cell.tier if cell else "assumption"
                prod_filled = cell.filled if cell else True
            cells.append(Cell(
                approach=approach, fmt=fkey, conv=_pcts(conv_eff), margin=_pcts(margin),
                conv_per_1000=float(np.median(conv_per_1000)),
                cost_per_conv=float(np.median(cost_per_conv)),
                prod_tier=prod_tier, prod_filled=prod_filled,
            ))

    # Leading approach = highest median conversions per krone across its formats.
    by_approach: dict[str, float] = {}
    best_cost: dict[str, float] = {}
    for c in cells:
        by_approach[c.approach] = max(by_approach.get(c.approach, -np.inf), c.conv_per_1000)
        best_cost[c.approach] = min(best_cost.get(c.approach, np.inf), c.cost_per_conv)
    leader = max(by_approach, key=by_approach.get) if by_approach else "ai_generated"

    # "Effectively level": the two leading approaches sit within ~5% on conversions
    # per krone, so the engine names no single leader.
    ranked = sorted(by_approach.items(), key=lambda kv: kv[1], reverse=True)
    level = (len(ranked) >= 2 and ranked[0][1] > 0
             and (ranked[0][1] - ranked[1][1]) / ranked[0][1] <= 0.05)
    level_pair = [ranked[0][0], ranked[1][0]] if level else []

    # Cost-per-sale sanity: approaches whose cheapest cell still costs more per
    # conversion than one conversion is worth.
    V_conv = scn.value_per_conversion_nok
    over_value = sorted((a for a, c in best_cost.items() if c > V_conv > 0),
                        key=lambda a: APPROACHES.index(a) if a in APPROACHES else 9)

    # ONE AI comparator used everywhere (break-even, brand line, sensitivity): AI's
    # strongest option on margin AT THE HUMAN'S format (like-for-like), falling back to
    # its strongest option on any format only when that format has no AI cell (e.g. a
    # studio headline). Named in the output so the single basis is explicit and the
    # three sections can never disagree.
    _at_hf = [o for o in ai_options if o["fmt"] == hf]
    _pool = _at_hf or ai_options
    ai_bench = max(_pool, key=lambda o: float(np.median(o["margin"]))) if _pool else None
    ai_bench_label = (f"{APPROACH_LABEL.get(ai_bench['approach'], ai_bench['approach'])} "
                      f"{formats[ai_bench['fmt']].label}") if ai_bench else ""

    breakeven = _break_even(scn, hf, costs, formats, impressions, base_ctr, base_cvr,
                            fmt_ctr, fmt_cvr, resp, V, R, draws, rng)
    breakeven_cost = _break_even_cost(scn, hf, formats, impressions, base_ctr, base_cvr,
                                      fmt_ctr, fmt_cvr, resp, mb, V, R, ai_bench, ai_bench_label)
    brand = _brand_line(scn, hf, costs, formats, impressions, base_ctr, base_cvr,
                        fmt_ctr, fmt_cvr, mb, mb_est, V, R, draws, rng, ai_bench, ai_bench_label)
    sens = _sensitivity(scn, hf, costs, formats, cpm_tri, ctr_e, cvr_e, resp_tri, V, R, ai_bench)
    roas = _roas_check(cells, leader, scn, roas_e, V)

    metrics = [
        MetricUse("CPM", cpm_e, bm.tag(cpm_e)),
        MetricUse("Click-through rate", ctr_e, bm.tag(ctr_e)),
        MetricUse("Conversion rate", cvr_e, bm.tag(cvr_e)),
        MetricUse("AI-vs-human response", resp_est, bm.tag(resp_est) if resp_est else "n/a"),
        MetricUse("Human memory/brand edge", mb_est, bm.tag(mb_est) if mb_est else "n/a"),
    ]
    confidence = _overall_confidence([cpm_e, ctr_e, cvr_e])

    notes: list[str] = []
    cap = scn.is_capacity_capped()
    if cap:
        reachable = (reach_p50 >= scn.capacity * 0.995) if scn.capacity else True
        if reachable:
            notes.append("Capacity-capped: the objective is the lowest cost to sell out, "
                         "not to maximise volume.")
        else:
            notes.append("Capacity-capped and the budget cannot reach capacity: the objective "
                         "is the lowest cost per sale, not to maximise volume.")
    if not breakeven.feasible:
        notes.append(f"No shared format for a like-for-like human-vs-AI break-even at "
                     f"{formats[hf].label}; shown for the nearest available cells.")
    return PlanResult(
        scenario=scn, headline_format=hf, leader=leader, cells=cells, breakeven=breakeven,
        breakeven_cost=breakeven_cost,
        brand=brand, sensitivity=sens, roas=roas, metrics=metrics, confidence=confidence,
        capacity_capped=cap, draws=draws, seed=seed,
        reach_p50=reach_p50, over_value=over_value, level=level, level_pair=level_pair,
        channel=scn.channel, notes=notes,
    )


def _approach_upfront(scn: Scenario, approach: str) -> float | None:
    """Upfront production cost (NOK) the advertiser supplied, if any, for an approach."""
    h = scn.costs.human.upfront()
    a = scn.costs.ai.upfront()
    if approach == "human_led":
        return h if h > 0 else None
    if approach == "ai_generated":
        return a if a > 0 else None
    if approach == "ai_assisted":
        if h > 0 and a > 0:
            return (h + a) / 2.0
    return None


def _override_format(scn: Scenario, formats: dict[str, Format], hf: str) -> str:
    """The format a supplied cost applies to: the scenario's `costs.format`, else the
    headline format. A supplied cost prices only this one format, not every cell."""
    f = scn.costs.format
    return f if (f and f in formats) else hf


def _override_amount(scn: Scenario, approach: str, fkey: str, ov_fmt: str) -> float | None:
    """The supplied upfront cost for (approach, fkey), or None if it does not apply here."""
    if fkey != ov_fmt:
        return None
    return _approach_upfront(scn, approach)


def _override_tri(scn: Scenario, approach: str, fkey: str, ov_fmt: str) -> Tri | None:
    """A supplied cost carried as a narrow ±15% band, so it can swing in the Monte
    Carlo and be named in sensitivity (a point value would have zero swing)."""
    amt = _override_amount(scn, approach, fkey, ov_fmt)
    if amt is None:
        return None
    return Tri(amt * (1 - OVERRIDE_SPREAD), amt, amt * (1 + OVERRIDE_SPREAD))


def _break_even(scn, hf, costs, formats, impressions, base_ctr, base_cvr,
                fmt_ctr, fmt_cvr, resp, V, R, draws, rng) -> BreakEven:
    f = formats[hf]
    feasible = "human_led" in f.approaches and "ai_generated" in f.approaches
    # AI conversions at the headline format (at its sampled response).
    rm_ai = resp
    conv_ai = impressions * base_ctr * fmt_ctr[hf] * rm_ai * base_cvr * fmt_cvr[hf]
    if scn.is_capacity_capped():
        conv_ai = np.minimum(conv_ai, scn.capacity)

    ov_fmt = _override_format(scn, formats, hf)

    def _cost(approach, fallback_fmt):
        ov = _override_tri(scn, approach, hf, ov_fmt)
        if ov is not None:
            return _draw(ov, draws, rng) / R
        c = costs.get((hf, approach)) or costs.get((fallback_fmt, approach))
        return _draw(c.nok, draws, rng) / R if c else np.zeros(draws)

    prod_h = _cost("human_led", "studio_shoot")
    prod_a = _cost("ai_generated", "ai_mockup")
    # prod_* are already amortised over reuse; lift = extra human prod per krone of
    # AI value, i.e. the fraction human response must beat AI by to match on margin.
    lift = (prod_h - prod_a) / np.maximum(V * conv_ai, 1e-9)
    return BreakEven(
        fmt=hf, lift=_pcts(lift), prod_human=float(np.median(prod_h)),
        prod_ai=float(np.median(prod_a)), conv_ai=float(np.median(conv_ai)), feasible=feasible,
    )


def _quote_placement(quote: float, funnel_p50: float, brand_p50: float) -> str:
    """Where a human-led quote sits relative to the two break-evens (funnel is the
    lower bound, brand-inclusive the higher). Position only - never a price to offer."""
    lo, hi = min(funnel_p50, brand_p50), max(funnel_p50, brand_p50)
    if quote > hi:
        return "above_both"
    if quote < lo:
        return "below_both"
    return "between"


def _break_even_cost(scn, hf, formats, impressions, base_ctr, base_cvr,
                     fmt_ctr, fmt_cvr, resp, mb, V, R, ai_bench, ai_label) -> BreakEvenCost:
    """Solve for the human-led production cost at which human-led matches the ONE
    shared AI comparator (``ai_bench`` - AI's strongest option) on margin, with the
    human at the scenario's (headline) format. Funnel only, and again with the human
    brand effect added (which raises the cost human-led can bear). Carried as
    p10/p50/p90. The same comparator is used by the brand line and sensitivity, so
    the three can never disagree."""
    f = formats[hf]
    feasible = "human_led" in f.approaches
    cap = scn.capacity if scn.is_capacity_capped() else None
    ov_fmt = _override_format(scn, formats, hf)

    def _conv(approach: str, fkey: str) -> np.ndarray:
        c = impressions * base_ctr * fmt_ctr[fkey] * _response_mult(approach, resp) * base_cvr * fmt_cvr[fkey]
        return np.minimum(c, cap) if cap is not None else c

    # Human-led at the headline format (or its best human-capable format if the
    # headline is AI-only, so a number always exists; feasible flags the caveat).
    h_fmt = hf if feasible else max(
        (k for k, ff in formats.items() if "human_led" in ff.approaches),
        key=lambda k: float(np.median(_conv("human_led", k))), default=hf)
    conv_h = _conv("human_led", h_fmt)

    draws = conv_h.shape[0]
    if ai_bench is None:                          # no AI cell at all: nothing to match
        z = np.zeros(draws)
        return BreakEvenCost(fmt=h_fmt, funnel=_pcts(z), with_brand=_pcts(z), feasible=feasible,
                             ai_label=ai_label)
    best_ai = ai_bench["margin"]                  # the ONE shared comparator

    # P solves  conv_h*V - budget - P/R == best_ai_margin ; brand adds human value.
    p_funnel = np.maximum(R * (conv_h * V - scn.budget_nok - best_ai), 0.0)
    p_brand = np.maximum(R * (conv_h * V * mb - scn.budget_nok - best_ai), 0.0)

    fp50, bp50 = float(np.median(p_funnel)), float(np.median(p_brand))

    # The scenario's own supplied human-led cost at the headline format is placed
    # automatically (same figure the human cells used). h_fmt == ov_fmt when the
    # headline is the priced format, which is the normal case now.
    own = _override_amount(scn, "human_led", h_fmt, ov_fmt)
    own_placement = _quote_placement(own, fp50, bp50) if (own and own > 0) else None

    # An optional override quote tests a different figure.
    quote = scn.human_quote_nok if (scn.human_quote is not None and scn.human_quote_nok > 0) else None
    placement = _quote_placement(quote, fp50, bp50) if quote is not None else None
    return BreakEvenCost(fmt=h_fmt, funnel=_pcts(p_funnel), with_brand=_pcts(p_brand),
                         feasible=feasible, ai_label=ai_label,
                         own_cost_nok=(own if own and own > 0 else None),
                         own_placement=own_placement, quote_nok=quote, placement=placement)


def _brand_line(scn, hf, costs, formats, impressions, base_ctr, base_cvr,
                fmt_ctr, fmt_cvr, mb, mb_est, V, R, draws, rng, ai_bench, ai_label) -> BrandLine:
    """The human brand gap, measured against the SAME comparator as the break-even
    (``ai_bench`` - AI's strongest option), so the two verdicts can never disagree."""
    ov_fmt = _override_format(scn, formats, hf)

    def _cost(approach, fallback_fmt):
        ov = _override_tri(scn, approach, hf, ov_fmt)
        if ov is not None:
            return _draw(ov, draws, rng) / R
        c = costs.get((hf, approach)) or costs.get((fallback_fmt, approach))
        return _draw(c.nok, draws, rng) / R if c else np.zeros(draws)

    conv_h = impressions * base_ctr * fmt_ctr[hf] * 1.0 * base_cvr * fmt_cvr[hf]
    if scn.is_capacity_capped():
        conv_h = np.minimum(conv_h, scn.capacity)
    margin_h = conv_h * V - scn.budget_nok - _cost("human_led", "studio_shoot")
    margin_a = ai_bench["margin"] if ai_bench is not None else margin_h   # the shared comparator
    gap = margin_a - margin_h                    # >0: AI ahead on the funnel alone
    brand_value = conv_h * V * (mb - 1.0)        # human long-term edge, NOT in the funnel
    worth = np.maximum(gap, 0.0)                 # kr the brand effect must be worth to close it
    return BrandLine(
        fmt=hf, funnel_gap=float(np.median(gap)), brand_value=float(np.median(brand_value)),
        worth_to_close=float(np.median(worth)), ai_label=ai_label,
        mb_tier=(mb_est.provenance if mb_est else "assumption"),
        mb_tag=(bm.tag(mb_est) if mb_est else "Assumption"),
    )


def _sensitivity(scn, hf, costs, formats, cpm_tri, ctr_e, cvr_e, resp_tri, V, R, ai_bench) -> list[Sensitivity]:
    """Which inputs move the break-even most, swept low->high at point otherwise. The
    AI side is the ONE shared comparator (``ai_bench`` - AI's strongest option), so
    "production cost (AI)" and the AI response/format are measured on the same basis
    the headline break-even and the brand line use."""
    ov_fmt = _override_format(scn, formats, hf)
    ai_fmt = ai_bench["fmt"] if ai_bench else hf
    ai_approach = ai_bench["approach"] if ai_bench else "ai_generated"
    af = formats[ai_fmt]
    half = ai_approach == "ai_assisted"           # hybrid response is midway to parity
    ch = costs.get((hf, "human_led")) or costs.get(("studio_shoot", "human_led"))
    ca = costs.get((ai_fmt, ai_approach)) or costs.get(("ai_mockup", "ai_generated"))
    ph = _override_amount(scn, "human_led", hf, ov_fmt)
    pa = _override_amount(scn, ai_approach, ai_fmt, ov_fmt)

    ctr_pt = _rate_to_fraction(ctr_e.point, ctr_e.unit)
    cvr_pt = _rate_to_fraction(cvr_e.point, cvr_e.unit)

    def point(name):
        return {
            "cpm": cpm_tri.point, "ctr": ctr_pt, "cvr": cvr_pt,
            "resp": resp_tri.point,
            "prod_human": (ph / R if ph is not None else (ch.nok.point / R if ch else 0.0)),
            "prod_ai": (pa / R if pa is not None else (ca.nok.point / R if ca else 0.0)),
            "ctr_mult": af.ctr_mult.point, "cvr_mult": af.cvr_mult.point,
        }[name]

    def lift(over):
        p = {k: point(k) for k in ("cpm", "ctr", "cvr", "resp", "prod_human", "prod_ai",
                                   "ctr_mult", "cvr_mult")}
        p.update(over)
        impr = scn.budget_nok / max(p["cpm"], 1e-9) * 1000.0
        rm = (1.0 + p["resp"]) / 2.0 if half else p["resp"]
        conv_ai = impr * p["ctr"] * p["ctr_mult"] * rm * p["cvr"] * p["cvr_mult"]
        return (p["prod_human"] - p["prod_ai"]) / max(V * conv_ai, 1e-9)

    base = lift({})
    ranges = {
        "production cost (human-led)": ("prod_human",
            (ph * (1 - OVERRIDE_SPREAD) / R if ph is not None else (ch.nok.low / R if ch else 0.0)),
            (ph * (1 + OVERRIDE_SPREAD) / R if ph is not None else (ch.nok.high / R if ch else 0.0))),
        "production cost (AI)": ("prod_ai",
            (pa * (1 - OVERRIDE_SPREAD) / R if pa is not None else (ca.nok.low / R if ca else 0.0)),
            (pa * (1 + OVERRIDE_SPREAD) / R if pa is not None else (ca.nok.high / R if ca else 0.0))),
        "CPM": ("cpm", cpm_tri.low, cpm_tri.high),
        "click-through rate": ("ctr", _rate_to_fraction(ctr_e.low, ctr_e.unit),
                               _rate_to_fraction(ctr_e.high, ctr_e.unit)),
        "conversion rate": ("cvr", _rate_to_fraction(cvr_e.low, cvr_e.unit),
                            _rate_to_fraction(cvr_e.high, cvr_e.unit)),
        "AI-vs-human response": ("resp", resp_tri.low, resp_tri.high),
    }
    out = []
    for label, (key, lo, hi) in ranges.items():
        swing = abs(lift({key: hi}) - lift({key: lo}))
        out.append(Sensitivity(driver=label, swing=float(swing)))
    out.sort(key=lambda s: s.swing, reverse=True)
    return out[:3]


def _roas_check(cells, leader, scn, roas_e, V) -> RoasCheck:
    lead_cells = [c for c in cells if c.approach == leader]
    if not lead_cells:
        return RoasCheck(implied=0.0, benchmark=None, note="no leading cell")
    best = max(lead_cells, key=lambda c: c.conv_per_1000)
    conv_p50 = best.conv[1]
    implied = conv_p50 * V / max(scn.budget_nok, 1e-9)
    bench = roas_e.point if roas_e else None
    note = "funnel-implied ROAS is a cross-check only; the roas benchmark is a wide D-tier assumption."
    if bench and (implied > bench * 2 or implied < bench / 2):
        note = (f"funnel-implied ROAS ~{implied:.1f} sits well outside the benchmark "
                f"~{bench:.1f}; treat the funnel figures as directional.")
    return RoasCheck(implied=float(implied), benchmark=bench, note=note)


def _overall_confidence(ests: list[bm.Estimate]) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    levels = [order[e.confidence] for e in ests if e]
    return {0: "low", 1: "medium", 2: "high"}[min(levels)] if levels else "low"
