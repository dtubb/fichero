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


def days_in_month(year: int, month: int, *, julian_calendar: bool = False) -> int:
    """How many days ``month`` has in ``year`` (0 for a month that does not exist).

    WHY: jdcal and convertdate accept 31 February and quietly return 3 March
    (#5514), so "Feb 31" became a real-looking date. Every parsed day is
    checked against this first; an impossible day is refused, never rolled.
    """
    if not 1 <= month <= 12:
        return 0
    if month == 2:
        if julian_calendar:
            leap = year % 4 == 0
        else:
            leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return (31, 0, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]


def julian_to_jdn(year: int, month: int, day: int) -> int:
    return int(julian.to_jd(year, month, day) + 0.5)


def french_republican_to_jdn(an: int, month: int, day: int) -> int:
    return int(french_republican.to_jd(an, month, day) + 0.5)


def hebrew_to_jdn(year: int, month: int, day: int) -> int:
    return int(hebrew.to_jd(year, month, day) + 0.5)


def islamic_to_jdn(year: int, month: int, day: int) -> int:
    return int(islamic.to_jd(year, month, day) + 0.5)


# THE document_date ordering (#3322): defined once, used by Database.search's
# sort AND the document listing routes. A second implementation — a client
# KeyPathComparator on dateJdn, an inline copy in another route — would carry
# different tie-breaking and different fallback, which is exactly the
# two-things-nothing-forces-to-agree class. Ties on start JDN break
# precise-first; undated docs fall back to created_at CONVERTED TO A JDN so
# one integer tuple orders the whole list; docs with neither sort first.
_PRECISION_RANK = {"day": 0, "month": 1, "year": 2, "circa": 3}


def document_date_sort_key(doc: Any) -> tuple[int, int, str]:
    """(jdn, precision_rank, name) for any object with date_jdn/date_meta/created_at.

    Name is the FINAL tiebreak (Daniel 2026-08-15: "document date then
    name") — same-day documents used to keep arbitrary insertion order, so
    the pages of one day shuffled between loads. Case-folded so scanner
    exports mixing IMG_/img_ interleave the way Finder shows them.
    """
    name = (getattr(doc, "name", "") or "").casefold()
    date_jdn = getattr(doc, "date_jdn", None)
    if date_jdn is not None:
        meta = getattr(doc, "date_meta", None) or {}
        return (int(date_jdn), _PRECISION_RANK.get(meta.get("precision", ""), 4), name)
    created = getattr(doc, "created_at", None)
    if created is not None:
        return (gregorian_to_jdn(created.year, created.month, created.day), 5, name)
    return (0, 9, name)


def _gregorian_iso(jdn: int) -> str:
    y, m, d = jdn_to_gregorian(jdn)
    return f"{y:04d}-{m:02d}-{d:02d}"


jdn_to_gregorian_iso = _gregorian_iso


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
    # Old English abbreviations, the superscript ending written on the line
    # (#5514: the 1913, 1942 and 1943 diaries were 37-50% undated for want of
    # "Jany", "Sepr", "Decr").
    "jany": 1, "janry": 1, "feby": 2, "febr": 2, "febry": 2, "apl": 4,
    "aprl": 4, "augt": 8, "sepr": 9, "septr": 9, "sepbr": 9, "octr": 10,
    "octbr": 10, "novr": 11, "novbr": 11, "decr": 12, "decbr": 12,
    # Spanish (Marshall diaries context)
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12, "ene": 1, "dic": 12,
}

#: Weekday names, Monday = 0: the JDN's own count (``jdn % 7``), so a written
#: weekday is checked against the date with no calendar library in between.
_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1,
    "wednesday": 2, "wednes": 2, "wed": 2, "thursday": 3, "thurs": 3,
    "thur": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2, "jueves": 3,
    "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}
_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                  "Saturday", "Sunday")

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
        if not 1 <= d <= days_in_month(y, mo):
            return None  # "1923-02-31" is no date, not 3 March (#5514)
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
        if month and not 1 <= day <= days_in_month(year, month, julian_calendar=assume_julian):
            return None  # an impossible day is refused, never rolled into the next month
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


# ---------------------------------------------------------------------------
# A page's own date: its heading (#5514)
# ---------------------------------------------------------------------------
#
# WHY a heading and not "the first date in the text": measured on the Marshall
# Diaries (#5514), a page dated from ANY date it mentions was wrong one time in
# ten: memoranda and cash pages took a money amount ("October 2.00"), almanac
# pages took an Act of 1894, and a scan that tried one pattern at a time let a
# later full-name date beat an abbreviated heading. A page is dated only by a
# HEADING: a line near the top that LEADS with the date (after an optional
# weekday, a short label such as "Lima," or one stray token before a weekday).
#
# The rules, each one a row in tests/unit/workflows/test_page_date_rules.py:
# - earliest heading wins, top lines first; a bare-year line ("1923") gives its
#   year to the headings below it and dates the page only if nothing else does;
# - the day is 1-2 digits and never runs into more digits: "FEBRUARY 1918" is
#   a month, not 19 February, and "October 2.00" is an amount, not a date;
# - the year may follow with or without a comma ("JANUARY 7 1918");
# - ordinals (1st, 2d, 3rd) and old abbreviations (Jany, Feby, Sepr, Decr);
# - numeric dates (1/3/23, Jan 3/23) read MONTH/DAY by default: these are
#   U.S. English diaries. A first number over 12 makes it day/month, a second
#   over 12 month/day; when both could be either, the default (or the caller's
#   ``day_first``) is used and recorded as assumed. A two-digit year takes the
#   century nearest the volume's year; with no volume year it is refused;
# - a year outside 1000-2100, an impossible day (31 February) or month is
#   refused and RECORDED as invalid; the page stays undated, never rolled;
# - a heading with no year takes the volume year passed in, marked inferred;
#   for a volume spanning several years, the written weekday picks the year;
#   when the weekday fits none (or several), that is flagged, never hidden;
# - a written weekday that disagrees with a written year is flagged, as is a
#   written year outside the volume's years (the 1919 volume's "1918"s);
# - pages headed MEMORANDA, CASH ACCOUNT, an almanac and the like are not
#   diary entries and are not dated from what they mention.

YEAR_MIN, YEAR_MAX = 1000, 2100
#: How far down a page a heading may sit: its first non-empty lines.
HEADING_LINES = 12

#: A non-entry page's title: the marker, then at most one more word ("CASH
#: ACCOUNT — JANUARY"), so an entry that begins "Cash paid to Smith" is not one.
_NON_ENTRY_RE = re.compile(
    r"^\W*(memoranda|memorandum|cash\s+account|cash|accounts?|bills\s+payable|"
    r"bills\s+receivable|addresses|almanac|postal\s+information|holidays|"
    r"telephone\s+numbers)\b[^a-z]*(?:[a-z]+[^a-z]*)?$",
    re.IGNORECASE,
)
_WORD = r"[a-zà-ÿ]+"
_LEAD_WEEKDAY_RE = re.compile(rf"(?P<wd>{_WORD})\.?\s*[,.]?\s*", re.IGNORECASE)
_JUNK_RE = re.compile(r"\S{1,4}\s+")
_LABEL_RE = re.compile(r"[^\d,.:;]{1,30}[,.:]\s+")
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th|d)?(?!\d)"
_YEAR_AFTER = r"(?:[\s,.]+(?P<year>\d{3,4})|/(?P<yy>\d{2}))(?!\d)"
_MONTH_DAY_RE = re.compile(rf"(?P<mon>{_WORD})\.?\s*,?\s+{_DAY}\.?(?:{_YEAR_AFTER})?", re.IGNORECASE)
_DAY_MONTH_RE = re.compile(
    rf"{_DAY}\.?\s+(?:de\s+|of\s+)?(?P<mon>{_WORD})\.?"
    r"(?:[\s,]+(?:de\s+)?(?P<year>\d{3,4})(?!\d))?",
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(r"(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>\d{4}|\d{2})(?!\d)")
_MONTH_YEAR_RE = re.compile(rf"(?P<mon>{_WORD})\.?\s*,?\s+(?P<year>\d{{4}})(?!\d)", re.IGNORECASE)
_YEARS_LINE_RE = re.compile(r"(?P<y1>\d{4})(?:\s*[-–—]\s*(?P<y2>\d{2}|\d{4}))?\W*$")
_TRAIL_WEEKDAY_RE = re.compile(rf"[\s,.\-–—]*(?P<wd>{_WORD})", re.IGNORECASE)
# The calendars only a rule parser reads, tried as whole headings first.
_EXOTIC_PATTERNS = [
    re.compile(r"\d{1,2}\s+[a-zà-ÿ]+\s+an\s+(?:[ivx]+|\d{1,2})\b", re.IGNORECASE),  # republican
    re.compile(r"\d{1,2}\s+[a-zà-ÿ]+\.?\s+\d{4}/\d{1,2}\b", re.IGNORECASE),  # OS double year
    re.compile(r"\d{4}-\d{2}-\d{2}\b"),  # ISO
]


@dataclass
class PageDate:
    """What a page's heading says: its date, the heading as written, and why not.

    ``invalid`` lists headings refused (impossible day, year out of range),
    each ``{"text", "reason"}``: a refused date is a fact about the page, not
    an absence. ``non_entry`` names the marker (MEMORANDA, CASH ACCOUNT) that
    kept a non-entry page undated.
    """

    date: HistoricalDate | None = None
    heading: str | None = None
    invalid: list[dict[str, str]] = field(default_factory=list)
    non_entry: str | None = None


def years_from_name(name: str | None) -> list[int]:
    """The years a volume or folder name covers: "NCM_Diary_19150108-19180628" -> 1915..1918.

    WHY every year of the span: the staging script took the FIRST year of a
    multi-year folder for every yearless heading (#5514: a 1915-18 volume dated
    entirely 1915). The candidates go to the weekday, which picks among them.
    A span over 50 years is not a volume and gives nothing.
    """
    found = [
        int(m.group(1))
        for m in re.finditer(r"(?<!\d)(\d{4})(?:\d{4})?(?!\d)", name or "")
        if YEAR_MIN <= int(m.group(1)) <= YEAR_MAX
    ]
    if not found:
        return []
    lo, hi = min(found), max(found)
    return list(range(lo, hi + 1)) if hi - lo <= 50 else []


def _weekday_of(word: str | None) -> int | None:
    return _WEEKDAYS.get((word or "").lower().rstrip("."))


def _heading_date(line: str) -> dict[str, Any] | None:
    """Read a heading-shaped line: the date must LEAD it. None = not a heading.

    What may come before the date: a weekday ("THURSDAY, Jan. 1, 1942"); one
    stray token of four characters or fewer, only before a weekday ("Ther FRI.
    JAN. 10, 1913"); or, on a short line (60 characters or fewer), a label of
    up to 30 characters ending in punctuation ("Lima, 15 de marzo de 1791").
    Anything longer before the date is prose MENTIONING a date: "Act of
    August 28, 1894", "having stopped since July 15."
    """
    # (where the heading's text starts, where its date starts, weekday written before it)
    starts: list[tuple[int, int, int | None]] = []

    def _with_weekday(at: int) -> None:
        wm = _LEAD_WEEKDAY_RE.match(line, at)
        if wm and _weekday_of(wm.group("wd")) is not None:
            starts.append((at, wm.end(), _weekday_of(wm.group("wd"))))

    _with_weekday(0)
    starts.append((0, 0, None))
    junk = _JUNK_RE.match(line)
    if junk:
        _with_weekday(junk.end())
    label = _LABEL_RE.match(line)
    if label and len(line) <= 60 and re.search(r"[a-zà-ÿ]", label.group(0), re.IGNORECASE):
        _with_weekday(label.end())
        starts.append((label.end(), label.end(), None))
    for text_start, pos, weekday in starts:
        found = _date_at(line, pos)
        if found is None:
            continue
        if found.get("weekday") is None:
            found["weekday"] = weekday
        found["text"] = line[text_start:found.pop("end")].strip(" ,;:-–—")
        return found
    return None


def _date_at(line: str, pos: int) -> dict[str, Any] | None:
    """The date that starts exactly at ``pos``, or None (an amount, a ledger row, prose)."""
    for pattern in _EXOTIC_PATTERNS:
        m = pattern.match(line, pos)
        if m:
            return {"kind": "exotic", "expr": m.group(0), "end": m.end()}
    m = _YEARS_LINE_RE.match(line, pos)
    if m:
        return {"kind": "years", "y1": m.group("y1"), "y2": m.group("y2"), "end": m.end()}
    found: dict[str, Any] | None = None
    m = _NUMERIC_RE.match(line, pos)
    if m:
        found = {"kind": "numeric", "a": int(m.group("a")), "b": int(m.group("b")),
                 "y": m.group("y"), "end": m.end()}
    else:
        for pattern in (_MONTH_DAY_RE, _DAY_MONTH_RE):
            m = pattern.match(line, pos)
            if m and _MONTHS.get(m.group("mon").lower()):
                groups = m.groupdict()
                found = {"kind": "day", "month": _MONTHS[m.group("mon").lower()],
                         "day": int(m.group("day")), "year": groups.get("year"),
                         "yy": groups.get("yy"), "end": m.end()}
                break
        if found is None:
            m = _MONTH_YEAR_RE.match(line, pos)
            if m and _MONTHS.get(m.group("mon").lower()):
                found = {"kind": "month", "month": _MONTHS[m.group("mon").lower()],
                         "year": m.group("year"), "end": m.end()}
    if found is None:
        return None
    rest = line[found["end"]:]
    # A number running on is a ledger row or an amount, not a heading:
    # "15 July 17 Dineen", "October 2.00", "2 May 150 sacks" (with no year).
    if re.match(r"\s*\d|[.,]\d", rest):
        return None
    trail = _TRAIL_WEEKDAY_RE.match(rest)
    if trail and _weekday_of(trail.group("wd")) is not None:
        found["weekday"] = _weekday_of(trail.group("wd"))
        found["end"] += trail.end()
    return found


def _invalid(text: str, reason: str) -> PageDate:
    return PageDate(heading=text, invalid=[{"text": text, "reason": reason}])


def _resolve_heading(
    line: str,
    h: dict[str, Any],
    *,
    volume_years: list[int],
    page_year: int | None,
    day_first: bool,
    year_start_march: bool,
    assume_julian: bool,
) -> PageDate:
    """Turn a read heading into a dated page, or a recorded refusal."""
    text = h["text"]
    calendar = "julian" if assume_julian else "gregorian"
    to_jdn = julian_to_jdn if assume_julian else gregorian_to_jdn
    flags: dict[str, Any] = {}

    if h["kind"] == "exotic":
        parsed = parse_historical_date(h["expr"], year_start_march=year_start_march,
                                       assume_julian=assume_julian)
        if parsed is None:
            return _invalid(line, "not a real date")
        parsed.meta["heading"] = line
        return PageDate(date=parsed, heading=line)

    def _check_year(year: int) -> str | None:
        if not YEAR_MIN <= year <= YEAR_MAX:
            return f"year {year} is outside {YEAR_MIN}-{YEAR_MAX}"
        return None

    def _volume_flag(year: int) -> None:
        if volume_years and year not in volume_years:
            flags["volume_year_conflict"] = {"written": year,
                                             "volume_years": [volume_years[0], volume_years[-1]]}

    if h["kind"] == "years":
        y1 = int(h["y1"])
        y2 = int(h["y2"]) if h["y2"] else y1
        if h["y2"] and len(h["y2"]) == 2:
            y2 = y1 // 100 * 100 + y2
        for y in (y1, y2):
            if (problem := _check_year(y)) is not None:
                return _invalid(line, problem)
        if y2 < y1:
            return _invalid(line, "the range ends before it starts")
        start, _ = _year_range_jdn(y1, calendar)
        _, end = _year_range_jdn(y2, calendar)
        date = _make(text, start, end, calendar=calendar, precision="year", confidence=0.8)
        date.meta["heading"] = line
        return PageDate(date=date, heading=line)

    if h["kind"] == "month":
        year = int(h["year"])
        if (problem := _check_year(year)) is not None:
            return _invalid(line, problem)
        _volume_flag(year)
        start, end = _month_range_jdn(year, h["month"], calendar)
        date = _make(text, start, end, calendar=calendar, precision="month")
        date.meta.update(heading=line, **flags)
        return PageDate(date=date, heading=line)

    # A day heading: month, day, and a year written, abbreviated or inferred.
    if h["kind"] == "numeric":
        a, b = h["a"], h["b"]
        if a > 12 and b > 12:
            return _invalid(line, f"neither {a} nor {b} can be a month")
        if a > 12:
            day, month, order = a, b, "day/month"
        elif b > 12:
            month, day, order = a, b, "month/day"
        elif day_first:
            day, month, order = a, b, "day/month (assumed)"
        else:
            month, day, order = a, b, "month/day (assumed)"
        flags["numeric_order"] = order
        raw_year = h["y"] if len(h["y"]) == 4 else None
        yy = h["y"] if len(h["y"]) == 2 else None
    else:
        month, day = h["month"], h["day"]
        raw_year, yy = h.get("year"), h.get("yy")

    weekday = h.get("weekday")
    year_source = "written"
    candidates: list[int] = []
    if raw_year:
        year = int(raw_year)
    elif yy:
        if not volume_years:
            return _invalid(line, "a two-digit year, and no volume year to give its century")
        anchor = volume_years[0]
        year = min((c * 100 + int(yy) for c in (anchor // 100 - 1, anchor // 100, anchor // 100 + 1)),
                   key=lambda y: abs(y - anchor))
        flags["year_expanded_from"] = yy
    elif page_year is not None:
        year, year_source = page_year, "page"
    elif volume_years:
        candidates = list(volume_years)
        year, year_source = candidates[0], "volume"
    else:
        return _invalid(line, "no year written and no volume year given")

    if (problem := _check_year(year)) is not None:
        return _invalid(line, problem)
    if not 1 <= month <= 12:
        return _invalid(line, f"there is no month {month}")
    if not 1 <= day <= days_in_month(year, month, julian_calendar=assume_julian):
        return _invalid(line, f"{_MONTH_NAMES[month - 1]} has no day {day}")

    if candidates:
        # Every candidate year's date must exist (29 Feb only in leap years).
        candidates = [y for y in candidates
                      if day <= days_in_month(y, month, julian_calendar=assume_julian)]
        if weekday is not None:
            fits = [y for y in candidates if to_jdn(y, month, day) % 7 == weekday]
            if fits:
                year, year_source = fits[0], "weekday" if len(candidates) > 1 else "volume"
                if len(fits) > 1:
                    flags["year_ambiguous"] = fits
            else:
                flags["weekday_conflict"] = {"written": _WEEKDAY_NAMES[weekday],
                                             "years_that_fit": []}
        elif len(candidates) > 1:
            flags["year_ambiguous"] = candidates
    elif weekday is not None and to_jdn(year, month, day) % 7 != weekday:
        fits = [y for y in volume_years if to_jdn(y, month, day) % 7 == weekday] if volume_years else []
        flags["weekday_conflict"] = {"written": _WEEKDAY_NAMES[weekday],
                                     "date_is": _WEEKDAY_NAMES[to_jdn(year, month, day) % 7],
                                     "years_that_fit": fits}
    if year_source == "written":
        _volume_flag(year)

    jdn = to_jdn(year, month, day)
    inferred = year_source in ("volume", "weekday", "page")
    display = f"{text} [{year}]" if inferred else None
    date = _make(text, jdn, jdn, calendar=calendar, precision="day",
                 confidence=0.7 if inferred else 0.9, display=display)
    date.meta.update(heading=line, year_source=year_source, year_inferred=inferred, **flags)
    return PageDate(date=date, heading=line)


_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December")


def find_page_date(
    text: str,
    *,
    volume_years: list[int] | tuple[int, ...] | None = None,
    day_first: bool = False,
    year_start_march: bool = False,
    assume_julian: bool = False,
    max_lines: int = HEADING_LINES,
) -> PageDate:
    """The date a page's own heading gives it, with what was refused and why.

    ``volume_years`` are the years the page's volume or folder covers (see
    ``years_from_name``): a yearless heading takes one, marked inferred.
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()][:max_lines]
    if not lines or is_explicitly_undated(lines[0]):
        return PageDate()
    for line in lines[:3]:
        marker = _NON_ENTRY_RE.match(line)
        if marker:
            return PageDate(non_entry=re.sub(r"\s+", " ", marker.group(1)).upper())
    years = sorted(set(volume_years or []))
    page_year: int | None = None
    fallback: tuple[str, dict[str, Any]] | None = None
    common = {"day_first": day_first, "year_start_march": year_start_march,
              "assume_julian": assume_julian}
    for line in lines:
        h = _heading_date(line)
        if h is None:
            continue
        if h["kind"] == "years":
            # A printed year at the top of the page: the year of the headings
            # below it, and the page's date only if no heading follows.
            if fallback is None:
                fallback = (line, h)
            if not h["y2"] and YEAR_MIN <= int(h["y1"]) <= YEAR_MAX:
                page_year = int(h["y1"])
            continue
        return _resolve_heading(line, h, volume_years=years, page_year=page_year, **common)
    if fallback is not None:
        return _resolve_heading(fallback[0], fallback[1], volume_years=years,
                                page_year=None, **common)
    return PageDate()


def extract_date_from_text(
    text: str,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
    max_chars: int = 4000,
    volume_years: list[int] | tuple[int, ...] | None = None,
    day_first: bool = False,
) -> HistoricalDate | None:
    """The page's heading date (``find_page_date``), or None."""
    if not text:
        return None
    return find_page_date(
        text[:max_chars],
        volume_years=volume_years,
        day_first=day_first,
        year_start_march=year_start_march,
        assume_julian=assume_julian,
    ).date


# ---------------------------------------------------------------------------
# A date a model wrote on a claim (#5514 K8)
# ---------------------------------------------------------------------------

_CLAIM_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


def check_claim_date(value: Any) -> tuple[str | None, str | None]:
    """(the date, None) when ``value`` is a real ISO date or range; (None, why) when not.

    WHY: a model that does not know the year echoes the prompt's format,
    and 157 Marshall claims stored "YYYY-08-17", "YYYY-11-36" or "<UNKNOWN>"
    as dates, which the timeline then plotted with no year. A claim date is
    "YYYY", "YYYY-MM", "YYYY-MM-DD" or "start/end" of those, with a real
    month and day and a year no later than 2100; anything else is refused
    with its reason, and the claim keeps no date. Empty is (None, None).
    """
    raw = str(value or "").strip()
    if not raw:
        return None, None
    parts = raw.split("/")
    if len(parts) > 2:
        return None, "not a date or a range of two dates"
    bounds: list[int] = []
    for part in parts:
        m = _CLAIM_DATE_RE.match(part.strip())
        if not m:
            return None, "a placeholder or unreadable value, not a date"
        y, mo, d = (int(g) if g else None for g in m.groups())
        if y > YEAR_MAX:
            return None, f"year {y} is after {YEAR_MAX}"
        if mo is not None and not 1 <= mo <= 12:
            return None, f"there is no month {mo}"
        if d is not None and not 1 <= d <= days_in_month(y, mo or 1):
            return None, f"{_MONTH_NAMES[(mo or 1) - 1]} {y} has no day {d}"
        bounds.append(gregorian_to_jdn(max(y, 1), mo or 1, d or 1))
    if len(bounds) == 2 and bounds[1] < bounds[0]:
        return None, "the range ends before it starts"
    return raw, None


def claim_date_jdn(value: str) -> int | None:
    """The first day a checked claim date names, as a JDN (None if it is not one)."""
    checked, _problem = check_claim_date(value)
    if checked is None:
        return None
    m = _CLAIM_DATE_RE.match(checked.split("/")[0].strip())
    if m is None:
        return None
    y, mo, d = (int(g) if g else None for g in m.groups())
    return gregorian_to_jdn(max(y, 1), mo or 1, d or 1)
