"""Seasonal demand effects around Norwegian calendar moments.

Turns the editable calendar in config into a per-date demand multiplier used by
the synthetic generator (more impressions, slightly higher CPMs around big
moments). The same moment definitions are reused by the opportunity module in
Phase 7, so the calendar lives in config and is parsed in one place.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class CalendarWindow:
    key: str
    label: str
    start: dt.date
    end: dt.date
    lead_time_weeks: int
    untested: bool = False

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end


def _moment_window_for_year(moment: dict, year: int) -> CalendarWindow | None:
    """Resolve a config moment into a concrete window for a given year."""
    key = moment["key"]
    label = moment.get("label", key)
    lead = int(moment.get("lead_time_weeks", 6))
    untested = bool(moment.get("untested", False))

    ranges = moment.get("ranges")
    if ranges and year in ranges:
        start_raw, end_raw = ranges[year]
        start = _as_date(start_raw)
        end = _as_date(end_raw)
        return CalendarWindow(key, label, start, end, lead, untested)

    if "month" in moment and "approx_day" in moment:
        month = int(moment["month"])
        day = min(int(moment["approx_day"]), 28)
        window_days = int(moment.get("window_days", 7))
        try:
            center = dt.date(year, month, day)
        except ValueError:
            return None
        half = window_days // 2
        return CalendarWindow(
            key, label, center - dt.timedelta(days=half), center + dt.timedelta(days=window_days - half),
            lead, untested,
        )
    return None


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def windows_for_years(cfg: dict, years: list[int]) -> list[CalendarWindow]:
    """All concrete calendar windows overlapping the given years."""
    moments = cfg.get("calendar", {}).get("moments", [])
    out: list[CalendarWindow] = []
    for moment in moments:
        for year in years:
            w = _moment_window_for_year(moment, year)
            if w is not None:
                out.append(w)
    return out


# Per-moment demand intensity (how much the moment lifts impressions at peak).
_MOMENT_INTENSITY: dict[str, float] = {
    "black_friday": 1.9,
    "advent_jul": 1.6,
    "julebord": 1.4,
    "syttende_mai": 1.5,
    "paske": 1.3,
    "russetid": 1.35,
    "fellesferie": 0.8,   # quieter buying period -> below baseline
    "back_to_school": 1.3,
    "vinterferie": 1.15,
    "first_snow": 1.2,
}


def demand_multiplier(day: dt.date, windows: list[CalendarWindow]) -> float:
    """Multiplicative demand factor for a date (1.0 = baseline).

    Peaks at the centre of a window and tapers linearly to the edges. Overlapping
    windows compound. A gentle weekly rhythm is layered on top.
    """
    mult = 1.0
    for w in windows:
        if not w.contains(day):
            continue
        span = max((w.end - w.start).days, 1)
        center = w.start + dt.timedelta(days=span // 2)
        dist = abs((day - center).days)
        closeness = max(0.0, 1.0 - dist / (span / 2 + 1))
        peak = _MOMENT_INTENSITY.get(w.key, 1.2)
        mult *= 1.0 + (peak - 1.0) * closeness
    # weekly rhythm: weekends slightly higher consumer attention
    if day.weekday() >= 5:
        mult *= 1.08
    return mult
