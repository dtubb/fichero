"""Historical document dates (#3322, plan #3319).

A diary page written in 1893 must sort by 1893, not by the day it was
scanned. The sort key is the **Julian Day Number** (JDN): a plain integer,
calendar-independent, timezone-immune — no ``datetime`` ever enters the sort
path. Imprecise dates are RANGES ("March 1791" spans the month; "An II"
spans the year), carried as ``(jdn, jdn_end)``; a day-precise date has
``jdn == jdn_end``.

Conversions go through ``convertdate`` and ``jdcal`` — never hand-rolled
calendar math. Regnal years and era names are DATA TABLES (precision=year),
not algorithms.

Three facts are kept distinct and must never be collapsed (a historian
needs all three): a date was extracted (``status="dated"``); the document
explicitly SAYS it is undated — "n.d.", "s.f.", "sine data"
(``status="undated_explicit"``); extraction ran and found nothing
(``status="none_found"``). "Never extracted" is the absence of any status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from convertdate import french_republican, hebrew, islamic, julian
from jdcal import gcal2jd, jd2gcal

# ---------------------------------------------------------------------------
# The value object
# ---------------------------------------------------------------------------

STATUS_DATED = "dated"
STATUS_UNDATED_EXPLICIT = "undated_explicit"
STATUS_NONE_FOUND = "none_found"


@dataclass
class HistoricalDate:
    """A parsed historical date: the verbatim string + a JDN range + meta."""

    original: str
    jdn: int | None
    jdn_end: int | None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_meta(self) -> dict[str, Any]:
        """The ``date_meta`` column payload."""
        return {"status": STATUS_DATED, **self.meta}


# ---------------------------------------------------------------------------
# JDN primitives (jdcal returns 2-part floats; we need the integer day)
# ---------------------------------------------------------------------------


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    a, b = gcal2jd(year, month, day)
    return int(a + b + 0.5)


def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    year, month, day, _frac = jd2gcal(jdn - 0.5, 0.0)
    return (year, month, int(day))


def julian_to_jdn(year: int, month: int, day: int) -> int:
    return int(julian.to_jd(year, month, day) + 0.5)


def french_republican_to_jdn(an: int, month: int, day: int) -> int:
    return int(french_republican.to_jd(an, month, day) + 0.5)


def hebrew_to_jdn(year: int, month: int, day: int) -> int:
    return int(hebrew.to_jd(year, month, day) + 0.5)


def islamic_to_jdn(year: int, month: int, day: int) -> int:
    return int(islamic.to_jd(year, month, day) + 0.5)


def _gregorian_iso(jdn: int) -> str:
    y, m, d = jdn_to_gregorian(jdn)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _month_range_jdn(year: int, month: int, calendar: str = "gregorian") -> tuple[int, int]:
    to_jdn = julian_to_jdn if calendar == "julian" else gregorian_to_jdn
    start = to_jdn(year, month, 1)
    if month == 12:
        end = to_jdn(year + 1, 1, 1) - 1
    else:
        end = to_jdn(year, month + 1, 1) - 1
    return start, end


def _year_range_jdn(year: int, calendar: str = "gregorian") -> tuple[int, int]:
    to_jdn = julian_to_jdn if calendar == "julian" else gregorian_to_jdn
    return to_jdn(year, 1, 1), to_jdn(year + 1, 1, 1) - 1


# ---------------------------------------------------------------------------
# Data tables — regnal years and era names (precision=year, flagged as such).
# Deliberately small seed tables; growing them is data entry, not code.
# ---------------------------------------------------------------------------

# monarch key -> accession YEAR (Gregorian). "3 Geo. II" = accession_year + 2.
REGNAL_ACCESSIONS: dict[str, int] = {
    "geo. i": 1714,
    "geo. ii": 1727,
    "geo. iii": 1760,
    "geo. iv": 1820,
    "vict.": 1837,
}

# era name (nianhao, transliterated or CJK) -> first YEAR of the era.
ERA_NAMES: dict[str, int] = {
    "康熙": 1662,  # Kangxi
    "kangxi": 1662,
    "乾隆": 1736,  # Qianlong
    "qianlong": 1736,
}

_CJK_NUMERALS = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                 "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_MONTHS = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # Spanish (Marshall diaries context)
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_FR_MONTHS = {
    "vendémiaire": 1, "vendemiaire": 1, "brumaire": 2, "frimaire": 3,
    "nivôse": 4, "nivose": 4, "pluviôse": 5, "pluviose": 5, "ventôse": 6,
    "ventose": 6, "germinal": 7, "floréal": 8, "floreal": 8, "prairial": 9,
    "messidor": 10, "thermidor": 11, "fructidor": 12,
}

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
          "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12, "xiii": 13,
          "xiv": 14}

# Explicitly-undated markers, the archival vocabulary: n.d. (no date),
# s.f. (sin fecha), s.d. (sine data / sans date).
_UNDATED_RE = re.compile(
    r"^\s*(?:n\.?\s?d\.?|s\.?\s?f\.?|s\.?\s?d\.?|sine\s+data|sin\s+fecha|sans\s+date|undated|no\s+date)\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def is_explicitly_undated(text: str) -> bool:
    """The document SAYS it has no date — a fact, not a failure."""
    return bool(_UNDATED_RE.match(text or ""))


def _make(original: str, jdn: int, jdn_end: int, *, calendar: str,
          precision: str, source: str = "extracted",
          confidence: float = 0.9, display: str | None = None) -> HistoricalDate:
    return HistoricalDate(
        original=original.strip(),
        jdn=jdn,
        jdn_end=jdn_end,
        meta={
            "calendar_system": calendar,
            "precision": precision,
            "converted_gregorian_iso": _gregorian_iso(jdn),
            "display": display or render_display(original.strip(), jdn, jdn_end, calendar, precision),
            "source": source,
            "confidence": confidence,
        },
    )


def render_display(original: str, jdn: int, jdn_end: int, calendar: str, precision: str) -> str:
    """Backend-rendered display string — the client never constructs a
    Foundation Date from a historical date (#3322 API contract)."""
    if calendar == "gregorian" and precision == "day":
        return original
    greg = _gregorian_iso(jdn)
    if precision in ("year", "circa") and jdn_end is not None and jdn_end != jdn:
        greg = f"{jdn_to_gregorian(jdn)[0]}"
    return f"{original} ({greg} Greg.)"


def parse_historical_date(
    text: str,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
) -> HistoricalDate | None:
    """Parse one date expression to a JDN range. None = not a date we read.

    ``year_start_march`` handles pre-1752 English Old Style double years
    ("10 Feb 1723/4" → the HISTORICAL year 1724, Julian calendar) — a
    parse-time concern, not a calendar. ``assume_julian`` treats plain
    day-month-year dates as Julian (pre-Gregorian sources).
    """
    if not text or not text.strip():
        return None
    s = text.strip()
    low = s.lower().strip(" .,;")

    circa = False
    m = re.match(r"^(?:circa|ca\.?|c\.)\s+(.*)$", low)
    if m:
        circa = True
        low = m.group(1).strip()

    # --- Old Style double year: "10 Feb 1723/4" or "10 February 1723/24"
    m = re.match(r"^(\d{1,2})\s+([a-z]+)\.?\s+(\d{4})/(\d{1,2})$", low)
    if m and year_start_march:
        day, mon_name, year_os, _year_ns = m.groups()
        month = _MONTHS.get(mon_name)
        if month:
            # The double year appears only for Jan–Mar 24 dates, where the
            # historical (New Style) year is OS year + 1. Julian calendar.
            year = int(year_os) + 1
            jdn = julian_to_jdn(year, month, int(day))
            return _make(s, jdn, jdn, calendar="julian", precision="day")

    # --- French Republican: "12 Thermidor An II" / "12 thermidor an 2"
    m = re.match(r"^(\d{1,2})\s+([a-zà-ÿ]+)\s+an\s+([ivx]+|\d{1,2})$", low)
    if m:
        day, fr_month, an_raw = m.groups()
        month = _FR_MONTHS.get(fr_month)
        an = _ROMAN.get(an_raw) if an_raw.isalpha() else int(an_raw)
        if month and an:
            jdn = french_republican_to_jdn(an, month, int(day))
            return _make(s, jdn, jdn, calendar="french_republican", precision="day")

    # --- Regnal: "3 Geo. II"
    m = re.match(r"^(\d{1,2})\s+(geo\.\s*(?:i{1,3}|iv)|vict\.)$", low)
    if m:
        regnal_year, monarch = m.groups()
        key = re.sub(r"\s+", " ", monarch)
        accession = REGNAL_ACCESSIONS.get(key)
        if accession:
            year = accession + int(regnal_year) - 1
            start, end = _year_range_jdn(year, "julian" if year < 1752 else "gregorian")
            return _make(s, start, end, calendar="regnal", precision="year", confidence=0.7)

    # --- Era name: "康熙三年" (Kangxi year 3) → 1664
    m = re.match(r"^(康熙|乾隆|kangxi|qianlong)\s*([元一二三四五六七八九十]+|\d{1,2})\s*(?:年)?$", s.strip(), re.IGNORECASE)
    if m:
        era, num_raw = m.groups()
        first_year = ERA_NAMES.get(era.lower() if era.isascii() else era)
        num = int(num_raw) if num_raw.isdigit() else _CJK_NUMERALS.get(num_raw)
        if first_year and num:
            year = first_year + num - 1
            start, end = _year_range_jdn(year)
            return _make(s, start, end, calendar="era_name", precision="year", confidence=0.7)

    # --- ISO: 1893-04-17
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", low)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        jdn = gregorian_to_jdn(y, mo, d)
        return _make(s, jdn, jdn, calendar="gregorian", precision="day")

    # --- "15 March 1791" / "15 de marzo de 1893" / "March 15, 1791"
    m = (
        re.match(r"^(\d{1,2})(?:\s+de)?\s+([a-zà-ÿ]+)\.?(?:\s+de)?\s+(\d{3,4})$", low)
        or re.match(r"^([a-zà-ÿ]+)\.?\s+(\d{1,2}),?\s+(\d{3,4})$", low)
    )
    if m:
        g = m.groups()
        if g[0].isdigit():
            day, mon_name, year = int(g[0]), g[1], int(g[2])
        else:
            mon_name, day, year = g[0], int(g[1]), int(g[2])
        month = _MONTHS.get(mon_name)
        if month:
            calendar = "julian" if assume_julian else "gregorian"
            to_jdn = julian_to_jdn if assume_julian else gregorian_to_jdn
            jdn = to_jdn(year, month, day)
            precision = "circa" if circa else "day"
            return _make(s, jdn, jdn, calendar=calendar, precision=precision)

    # --- "March 1791" (month precision → range)
    m = re.match(r"^([a-zà-ÿ]+)\.?(?:\s+de)?\s+(\d{3,4})$", low)
    if m:
        mon_name, year = m.group(1), int(m.group(2))
        month = _MONTHS.get(mon_name)
        if month:
            calendar = "julian" if assume_julian else "gregorian"
            start, end = _month_range_jdn(year, month, calendar)
            return _make(s, start, end, calendar=calendar, precision="month")

    # --- bare year "1791" (year precision → range)
    m = re.match(r"^(\d{3,4})$", low)
    if m:
        year = int(m.group(1))
        if 100 <= year <= 2200:
            start, end = _year_range_jdn(year, "julian" if assume_julian else "gregorian")
            precision = "circa" if circa else "year"
            return _make(s, start, end,
                         calendar="julian" if assume_julian else "gregorian",
                         precision=precision,
                         confidence=0.6 if circa else 0.8)

    return None


# Date-looking substrings inside running text, tried in specificity order.
_SCAN_PATTERNS = [
    r"\b\d{1,2}\s+[a-zà-ÿ]+\s+an\s+(?:[ivx]+|\d{1,2})\b",  # republican
    r"\b\d{1,2}\s+[a-zà-ÿ]+\.?\s+\d{4}/\d{1,2}\b",          # OS double year
    r"\b\d{4}-\d{2}-\d{2}\b",                                # ISO
    r"\b\d{1,2}(?:\s+de)?\s+[a-zà-ÿ]+\.?(?:\s+de)?\s+\d{3,4}\b",
    r"\b[a-zà-ÿ]+\.?\s+\d{1,2},\s+\d{3,4}\b",
    r"\b[a-zà-ÿ]{3,}\.?\s+\d{4}\b",
]


def extract_date_from_text(
    text: str,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
    max_chars: int = 4000,
) -> HistoricalDate | None:
    """First parseable date expression in running text (headers first).

    Scans only the head of the text: a diary entry's date is at the top,
    and scanning a whole book finds every date it mentions.
    """
    if not text:
        return None
    head = text[:max_chars]
    if is_explicitly_undated(head.strip().splitlines()[0] if head.strip() else ""):
        return None
    for pattern in _SCAN_PATTERNS:
        for m in re.finditer(pattern, head, re.IGNORECASE):
            parsed = parse_historical_date(
                m.group(0),
                year_start_march=year_start_march,
                assume_julian=assume_julian,
            )
            if parsed is not None:
                return parsed
    return None
