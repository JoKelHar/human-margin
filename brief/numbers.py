# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""The no-naked-numbers engine: find every quantitative number in a text and check it
against the available Figures.

A number passes only if some Figure has a compatible unit and a value that rounds, at the
number's own precision, to the number as written. Handles kr and percent (incl. Norwegian
formats like "3.900 kr", "kr 3 900,-", "1,5 %", "4 mill", "3,9k"), ranges, bare counts
with a unit alias (orders/bestillinger/ordrer...), number words (en + no), and
multipliers (double/triple/half, dobbel/tredobbel/halvparten). Years are whitelisted only
in a date context; a bare 4-digit number is checked like any other.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# --- units -------------------------------------------------------------------
# Surface form -> canonical unit. Figures use canonical units (NOK, percent, and the
# sale nouns). "No value-only matching": a count must match a Figure of the same unit.
UNIT_ALIASES = {
    "kr": "NOK", "nok": "NOK", "kroner": "NOK",
    "%": "percent", "percent": "percent", "prosent": "percent", "pct": "percent",
    "order": "orders", "orders": "orders", "ordre": "orders", "ordrer": "orders",
    "bestilling": "orders", "bestillinger": "orders",
    "membership": "memberships", "memberships": "memberships",
    "medlemskap": "memberships",
    "booking": "bookings", "bookings": "bookings",
    "sign-up": "sign-ups", "sign-ups": "sign-ups", "signup": "sign-ups",
    "signups": "sign-ups", "paamelding": "sign-ups", "paameldinger": "sign-ups",
    "campaign": "campaigns", "campaigns": "campaigns", "kampanje": "campaigns",
    "kampanjer": "campaigns",
    "x": "x",
}

# Number words (English + Norwegian), enough for brief copy.
_UNITS_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
    "null": 0, "en": 1, "ett": 1, "to": 2, "tre": 3, "fire": 4, "fem": 5, "seks": 6,
    "sju": 7, "syv": 7, "aatte": 8, "ni": 9, "ti": 10, "elleve": 11, "tolv": 12,
    "tretten": 13, "fjorten": 14, "femten": 15, "seksten": 16, "sytten": 17,
    "atten": 18, "nitten": 19, "tjue": 20,
}
_SCALE_WORDS = {"hundred": 100, "hundre": 100, "thousand": 1000, "tusen": 1000}
MULTIPLIERS = {"double": 2.0, "triple": 3.0, "twice": 2.0, "half": 0.5,
               "dobbel": 2.0, "dobbelt": 2.0, "tredobbel": 3.0, "halvparten": 0.5}

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december",
           "januar", "februar", "mars", "mai", "juni", "juli", "august",
           "september", "oktober", "november", "desember")


def _fold(s: str) -> str:
    """Lowercase and strip Norwegian diacritics so 'påmeldinger'/'åtte' match the tables."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass(frozen=True)
class Num:
    value: float
    unit: str | None          # canonical unit, or None when the text gave none
    raw: str
    decimals: int             # decimal places as written (0 for an integer token)
    trailing_zeros: int       # trailing zeros of an integer token (rounding granularity)


def _parse_numeric(raw: str) -> float | None:
    """Parse a numeric string that may use Norwegian or English grouping/decimals."""
    s = raw.replace(" ", " ").strip().replace(" ", "")
    mult = 1.0
    m = re.search(r"(mill(?:ion)?|mrd|k)$", s)
    if m:
        mult = {"k": 1e3, "mill": 1e6, "million": 1e6, "mrd": 1e9}[m.group(1)]
        s = s[: m.start()]
    s = s.rstrip(",-").rstrip(".")
    if not s:
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:                       # last separator is the decimal
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        s = s.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif has_comma:                                 # 1,5 -> decimal; 3,900 -> grouping
        s = s.replace(",", "" if re.search(r",\d{3}$", s) else ".")
    elif has_dot:                                   # 3.900 -> grouping; 42.5 -> decimal
        if re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")
    try:
        return float(s) * mult
    except ValueError:
        return None


def _precision(raw: str) -> tuple[int, int]:
    """(decimal places, trailing zeros) of the number as written, for the rounding check."""
    body = re.sub(r"[^\d.,]", "", raw.replace(" ", " ").replace(" ", "")).rstrip(",-")
    sep = max(body.rfind("."), body.rfind(","))
    frac = body[sep + 1:] if sep != -1 and len(body) - sep - 1 in (1, 2) else ""
    if frac:
        return len(frac), 0
    digits = re.sub(r"\D", "", body)
    tz = len(digits) - len(digits.rstrip("0")) if digits else 0
    return 0, tz


def rounds_to(fig_value: float, num: Num) -> bool:
    """True if fig_value, rounded at num's own precision, equals num.value."""
    def r(places: int) -> float:
        q = Decimal(1).scaleb(-places)
        return float(Decimal(str(fig_value)).quantize(q, rounding=ROUND_HALF_UP))
    if num.decimals:
        return r(num.decimals) == round(num.value, num.decimals)
    for k in range(0, num.trailing_zeros + 1):       # nearest 1, 10, ... 10^tz
        if r(-k) == num.value:
            return True
    return False


_NUM = r"\d[\d  .,]*\d|\d"


def _canonical_unit(word: str) -> str | None:
    return UNIT_ALIASES.get(_fold(word).rstrip("."))


def _year_in_date_context(text: str, start: int, token: str) -> bool:
    """A bare 4-digit year is whitelisted only next to a month or 'in/i'."""
    if not re.fullmatch(r"\d{4}", token):
        return False
    before = _fold(text[max(0, start - 14):start])
    after = _fold(text[start + len(token):start + len(token) + 12])
    if re.search(r"\b(in|i)\s*$", before) or re.search(r"^\s*(in|i)\b", after):
        return True
    return any(mo in before or mo in after for mo in _MONTHS)


def extract(text: str) -> list[Num]:
    """Every quantitative number in the text (ranges expand to both endpoints)."""
    nums: list[Num] = []
    folded = _fold(text)

    # Number words and multipliers.
    for m in re.finditer(r"[a-zæøå]+", folded):
        w = m.group(0)
        if w in MULTIPLIERS:
            nums.append(Num(MULTIPLIERS[w], "x", w, 0, 0))
        elif w in _UNITS_WORDS and w not in ("en", "to", "i"):   # skip words that are also NO prepositions/articles
            val = _UNITS_WORDS[w]
            scale_after = folded[m.end():m.end() + 8].strip().split(" ")[0] if folded[m.end():].strip() else ""
            if scale_after in _SCALE_WORDS:
                val *= _SCALE_WORDS[scale_after]
            nums.append(Num(float(val), None, w, 0, 0))

    # Digit tokens: ranges, then currency/percent/counts, then bare.
    for m in re.finditer(rf"({_NUM})\s*[–—-]\s*({_NUM})\s*(kr|nok|%|prosent)?", text, re.I):
        a, b = _parse_numeric(m.group(1)), _parse_numeric(m.group(2))
        unit = _canonical_unit(m.group(3)) if m.group(3) else None
        for g, v in ((1, a), (2, b)):
            if v is not None:
                dp, tz = _precision(m.group(g))
                nums.append(Num(v, unit, m.group(g), dp, tz))

    consumed = text  # mask ranges so their endpoints are not re-read as singletons
    consumed = re.sub(rf"(?:{_NUM})\s*[–—-]\s*(?:{_NUM})",
                      lambda mm: "#" * len(mm.group(0)), consumed)

    for m in re.finditer(rf"(kr\s*)?({_NUM})\s*(kr|nok|%|prosent|,-)?\s*([a-zæøå\-]+)?", consumed, re.I):
        if not m.group(2):
            continue
        val = _parse_numeric(m.group(2))
        if val is None:
            continue
        pre, suf, word = m.group(1), (m.group(3) or ""), (m.group(4) or "")
        dp, tz = _precision(m.group(2))
        if _year_in_date_context(consumed, m.start(2), m.group(2).strip()):
            continue
        if pre or suf.lower() in ("kr", "nok", ",-"):
            unit = "NOK"
        elif suf in ("%",) or suf.lower() in ("prosent",):
            unit = "percent"
        else:
            unit = _canonical_unit(word) if word else None
        nums.append(Num(val, unit, m.group(2).strip(), dp, tz))
    return nums


def unmatched(text: str, figures: list[tuple[float, str]]) -> list[str]:
    """Numbers in `text` not backed by any Figure (value+unit). Empty = clean."""
    figs = [(float(v), u) for v, u in figures]
    bad: list[str] = []
    for n in extract(text):
        ok = False
        for fv, fu in figs:
            unit_ok = n.unit is None or n.unit == fu
            if unit_ok and rounds_to(fv, n):
                ok = True
                break
        if not ok:
            bad.append(f"{n.raw!r}" + (f" ({n.unit})" if n.unit else ""))
    return bad


__all__ = ["Num", "extract", "unmatched", "rounds_to", "UNIT_ALIASES", "MULTIPLIERS"]
