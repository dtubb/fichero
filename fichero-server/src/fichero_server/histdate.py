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
_PRECISION_RANK = {"day": 0, "month": 1, "year": 2, "range": 2, "circa": 3}


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
# - numeric dates (1/3/23): a first number over 12 makes it day/month, a
#   second over 12 month/day. When both could be either, the order comes from
#   the LANGUAGE (``day_first_for_languages``): en-US reads month/day; en-GB and
#   every other language day/month (most of the archives here are Spanish and
#   Colombian). The caller's ``day_first`` is an explicit override. With no
#   language known, both readings are recorded in ``PageDate.ambiguous`` and
#   the page is not dated: a guess here moves a page by up to eleven months.
#   "Jan 3/23" names its month and is never ambiguous. A two-digit year takes
#   the century nearest the volume's year; with no volume year it is refused;
# - a year outside 1000-2100, an impossible day (31 February) or month is
#   refused and RECORDED as invalid; the page stays undated, never rolled;
# - a heading with no year takes the volume year passed in, marked inferred;
#   for a volume spanning several years, the written weekday picks the year;
#   when the weekday fits none (or several), that is flagged, never hidden;
# - a written weekday that disagrees with a written year is flagged, as is a
#   written year outside the volume's years (the 1919 volume's "1918"s);
# - but when the written weekday AND the volume's year agree against the
#   written year, they win (ruled by the maintainer, #5518): the date takes the
#   volume year, the written year is kept beside it (``written_year``,
#   ``year_overruled``) and the year is shown in brackets as supplied;
# - pages headed MEMORANDA, CASH ACCOUNT, an almanac and the like are not
#   diary entries and are not dated from what they mention ("May Cash
#   Account", "MOON'S PHASES" and "LEGAL HOLIDAYS" too, #5518).
# Found re-dating a copy of the Marshall Diaries (#5518), also rows in
# tests/unit/workflows/test_diary_dates_5518.py:
# - a full heading may close a line after a printed running header ("Seattle
#   Office. Vice-Consul. WEDNESDAY, APRIL 24, 1940");
# - a page number may follow a written year ("MAY 13. 1918 12"), unless the
#   weekday then fits no year, which marks the line as garbled;
# - "Dec.4" reads as "Dec. 4"; a yearless date followed by another date is a
#   register row ("Sept.5 Sept24 June26"), not a heading;
# - a margin label ("Mar. 23") gives way to the full heading of the same day
#   on the next lines ("Saturday, March 23, 1918");
# - with no heading near the top, the first line further down that leads with
#   a date and a weekday dates the page ("Sunday February 14th - Ran aground").
# The rerun on a fresh clone (#5557), rows in test_diary_dates_5557.py:
# - in a volume of several years a yearless heading follows page order: the
#   year of the dated page before it, the next when the months wrap; kept inside
#   the volume name's full date range (``_year_from_page_order``);
# - a margin label alone on its line gives way to a full heading a day or two
#   off it; "MONDAY. 1918 MARCH 31" is read; OCR damage ("FEBRUARY 21918",
#   "OCTOBE 3") only when the weekday confirms;
# - "Novembe / Cash Account Received Paid", the printed MEMORANDA head in OCR
#   debris, a recapitulation, and a date or year line more than a year from the
#   volume's do not date a page; "11/16/23" in 1943-45 is refused;
# - "Jan 1, 1932 - Dec 31, 1932" is a range, not 1 January.

YEAR_MIN, YEAR_MAX = 1000, 2100
#: How far down a page a heading may sit: its first non-empty lines.
HEADING_LINES = 12

#: A non-entry page's title: the marker, then at most one more word ("CASH
#: ACCOUNT — JANUARY"), so an entry that begins "Cash paid to Smith" is not one.
#: A month name may come first ("May Cash Account", #5518), never a year: the
#: 1914 diary's "April 1914 Cash Account Received Paid" is a week of entries
#: with a cash column. The printed almanac pages ("MOON'S PHASES", the
#: "CALENDAR. VALUES OF FOREIGN COINS" table that quotes an Act of 1894) are
#: not entries either (#5518).
_NON_ENTRY_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NON_ENTRY_RE = re.compile(
    rf"^\W*(?:(?:{_NON_ENTRY_MONTH})\.?\s+)?"
    r"(memoranda|memorandum|cash\s+account|cash|accounts?|bills\s+payable|"
    r"bills\s+receivable|addresses|almanac|postal\s+information|holidays|"
    r"telephone\s+numbers|legal\s+holidays|moon'?s\s+phases|phases\s+of\s+the\s+moon|calendar|"
    r"values\s+of\s+foreign\s+coins|recapitulation)\b[^a-z]*(?:[a-z]+[^a-z]*)?$",
    re.IGNORECASE,
)
#: The printed column heads of a week page's cash column, alone on a line
#: ("Novembe / Cash Account Received Paid", #5557). Under a month AND year
#: ("May 1914") the page is a week of entries dated by that month; under a
#: bare or OCR-cut month name nothing dates it, and the days below it are the
#: cash column's, so it stays undated as a cash page.
_CASH_COLUMNS_RE = re.compile(r"^\W*cash\s+account\s+received\s+paid\W*$", re.IGNORECASE)
#: The printed MEMORANDA head with OCR debris around it ("Act with MEMORANDA
#: very", #5557): the capitals are the printed head; "memoranda" in a
#: sentence is a word, not a title.
_PRINTED_MEMORANDA_RE = re.compile(r"^(?:\S+\s+){0,3}MEMORANDA\b\W*(?:\S+\W*)?$")
_WORD = r"[a-zà-ÿ]+"
_LEAD_WEEKDAY_RE = re.compile(rf"(?P<wd>{_WORD})\.?\s*[,.]?\s*", re.IGNORECASE)
_JUNK_RE = re.compile(r"\S{1,4}\s+")
_LABEL_RE = re.compile(r"[^\d,.:;]{1,30}[,.:]\s+")
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th|d)?(?!\d)"
_YEAR_AFTER = r"(?:[\s,.]+(?P<year>\d{3,4})|/(?P<yy>\d{2}))(?!\d)"
# "Dec.4" (no space after the full stop, #5518) reads like "Dec. 4"; a month
# word with no full stop still needs a space before its day.
_MONTH_DAY_RE = re.compile(
    rf"(?P<mon>{_WORD})(?:\.\s*,?\s*|\s*,?\s+){_DAY}\.?(?:{_YEAR_AFTER})?", re.IGNORECASE
)
#: A page number printed after a written year ("MAY 13. 1918 12"), to the end
#: of the line: not a ledger amount (#5518).
_TRAIL_PAGE_NUMBER_RE = re.compile(r"\s+\d{1,3}\s*$")
_DAY_MONTH_RE = re.compile(
    rf"{_DAY}\.?\s+(?:de\s+|of\s+)?(?P<mon>{_WORD})\.?"
    r"(?:[\s,]+(?:de\s+)?(?P<year>\d{3,4})(?!\d))?",
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(r"(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>\d{4}|\d{2})(?!\d)")
#: The year before the month, after a weekday: "MONDAY. 1918 MARCH 31" (#5557).
_YEAR_MONTH_DAY_RE = re.compile(
    rf"(?P<year>\d{{4}})\s*[,.]?\s+(?P<mon>{_WORD})\.?\s*,?\s*{_DAY}\.?", re.IGNORECASE
)
#: A day run into its year by OCR: "FEBRUARY 21918" (#5557), read only when the
#: weekday written before it confirms exactly one reading.
_MONTH_DIGITS_RE = re.compile(rf"(?P<mon>{_WORD})\.?\s*,?\s+(?P<digits>\d{{5,6}})(?!\d)", re.IGNORECASE)
#: Between the two ends of a written range: "Jan 1, 1932 - Dec 31, 1932" (#5557).
_RANGE_SEP_RE = re.compile(r"\s*(?:[-–—]+|to)\s*", re.IGNORECASE)
#: Full English month names, for a name the OCR cut short ("OCTOBE 3", #5557).
_FULL_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december")
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
    kept a non-entry page undated. ``ambiguous`` lists a numeric heading whose
    day/month order no language settles, ``{"text", "readings": [...]}`` with
    both readings, so a person can choose; the page is left undated.
    """

    date: HistoricalDate | None = None
    heading: str | None = None
    invalid: list[dict[str, str]] = field(default_factory=list)
    non_entry: str | None = None
    ambiguous: list[dict[str, Any]] = field(default_factory=list)


def day_first_for_language(tag: str | None) -> bool | None:
    """Whether a language writes numeric dates day first: False for en-US, True for every
    other language (en-GB, es, es-CO, fr…), None when the tag does not say.

    WHY bare "en" is None: English writes both orders (U.S. month/day, British
    day/month), so "en" alone cannot settle 1/3/23; nor can "und" or nothing.
    """
    norm = (tag or "").strip().lower().replace("_", "-")
    if not norm or norm in ("en", "eng", "und", "unknown", "mul", "zxx"):
        return None
    if norm == "en-us" or norm.startswith("en-us-"):
        return False
    return True


def day_first_for_languages(document_language: str | None,
                            project_languages: list[str] | tuple[str, ...] | None = None) -> bool | None:
    """The order for ambiguous numeric dates: the document's language, else the project's setup
    languages (only when they all agree), else None (unknown: record both readings)."""
    own = day_first_for_language(document_language)
    if own is not None:
        return own
    orders = {day_first_for_language(t) for t in project_languages or ()}
    orders.discard(None)
    return orders.pop() if len(orders) == 1 else None


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


def range_from_name(name: str | None) -> tuple[int, int] | None:
    """The first and last day a volume name gives, as JDNs: "NCM_Diary_19431017-19450922".

    WHY the full dates and not only the years (#5557): the 1943-45 volume
    begins on 17 October 1943, and its yearless "Feb 27", "Mar 12" were dated
    1943, eight months before the volume begins. None when the name does not
    give two real YYYYMMDD dates in order.
    """
    m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})\s*[-–_]\s*(\d{4})(\d{2})(\d{2})(?!\d)", name or "")
    if not m:
        return None
    y1, m1, d1, y2, m2, d2 = (int(g) for g in m.groups())
    for y, mo, d in ((y1, m1, d1), (y2, m2, d2)):
        if not (YEAR_MIN <= y <= YEAR_MAX and 1 <= d <= days_in_month(y, mo)):
            return None
    start, end = gregorian_to_jdn(y1, m1, d1), gregorian_to_jdn(y2, m2, d2)
    return (start, end) if start <= end else None


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
        found = _date_at(line, pos, weekday)
        if found is None:
            continue
        if found.get("weekday") is None:
            found["weekday"] = weekday
        found["text"] = line[text_start:found.pop("end")].strip(" ,;:-–—")
        return found
    return _closing_heading(line)


def _closing_heading(line: str) -> dict[str, Any] | None:
    """A full heading that ENDS a line after a running header, or None.

    "Seattle Office. Vice-Consul. WEDNESDAY, APRIL 24, 1940" (#5518): the
    printed header sits on the heading's line, so the heading does not lead it,
    and the page took the NEXT day's heading. Only a weekday, a month, a day
    and a written year that close the line (a page number may follow) count:
    prose mentioning "Wednesday, April 24, 1940 we sailed" goes on after it.
    """
    for m in re.finditer(rf"(?<![a-zà-ÿ]){_WORD}", line, re.IGNORECASE):
        if m.start() == 0 or _weekday_of(m.group(0)) is None:
            continue
        wm = _LEAD_WEEKDAY_RE.match(line, m.start())
        found = _date_at(line, wm.end(), _weekday_of(m.group(0))) if wm else None
        if found is None or found["kind"] != "day" or not found.get("year"):
            continue
        rest = line[found["end"]:]
        if rest.strip() and not _TRAIL_PAGE_NUMBER_RE.match(rest):
            continue
        if found.get("weekday") is None:
            found["weekday"] = _weekday_of(m.group(0))
        found["text"] = line[m.start():found.pop("end")].strip(" ,;:-–—")
        found["closing"] = True
        return found
    return None


def _weekday_fits(h: dict[str, Any], volume_years: list[int], assume_julian: bool) -> bool:
    """Whether a day heading's written weekday fits its written year or a volume year.

    True when no weekday is written: there is nothing to contradict.
    """
    if h.get("weekday") is None:
        return True
    to_jdn = julian_to_jdn if assume_julian else gregorian_to_jdn
    month, day = h["month"], h["day"]
    years = {int(h["year"]), *volume_years} if h.get("year") else set(volume_years)
    return any(1 <= month <= 12 and 1 <= day <= days_in_month(y, month, julian_calendar=assume_julian)
               and to_jdn(y, month, day) % 7 == h["weekday"] for y in years)


def _is_margin_label(h: dict[str, Any]) -> bool:
    """A day heading with neither a weekday nor a year: "Mar. 23" in the margin."""
    return (h["kind"] == "day" and h.get("weekday") is None
            and not h.get("year") and not h.get("yy"))


def _cut_month(word: str) -> int | None:
    """The month an OCR-cut name stands for ("OCTOBE", "Novembe"), or None.

    Five letters or more, the start of exactly one full English month name and
    not a name already read. Only used after a written weekday, which must then
    fit the date (#5557).
    """
    low = word.lower()
    if len(low) < 5 or low in _MONTHS:
        return None
    hits = [i + 1 for i, name in enumerate(_FULL_MONTHS) if name.startswith(low)]
    return hits[0] if len(hits) == 1 else None


def _ocr_day_year(month: int, digits: str, weekday: int) -> tuple[int, str] | None:
    """(day, year) for a day run into its year ("21918" → 21, 1918), or None.

    The readings: one digit of day and four of year ("2" "1918"); two of day
    sharing a digit with the year ("21" "1918", the OCR dropped the space and a
    "1"); two of day, four of year ("21" "1918" from "211918"). Only a reading
    whose date falls on the written weekday counts, and only when exactly one
    does (#5557).
    """
    readings = ([(digits[0], digits[1:]), (digits[:2], digits[1:])] if len(digits) == 5
                else [(digits[:2], digits[2:])])
    fits = []
    for d, y in readings:
        day, year = int(d), int(y)
        if (YEAR_MIN <= year <= YEAR_MAX and 1 <= day <= days_in_month(year, month)
                and gregorian_to_jdn(year, month, day) % 7 == weekday):
            fits.append((day, y))
    return fits[0] if len(set(fits)) == 1 else None


def _date_at(line: str, pos: int, weekday: int | None = None) -> dict[str, Any] | None:
    """The date that starts exactly at ``pos``, or None (an amount, a ledger row, prose).

    ``weekday`` is the weekday written just before ``pos``: only then are the
    year-first form ("MONDAY. 1918 MARCH 31") and the OCR repairs ("FEBRUARY
    21918", "OCTOBE 3") read, each checked against it (#5557).
    """
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
    elif weekday is not None and (m := _YEAR_MONTH_DAY_RE.match(line, pos)) \
            and _MONTHS.get(m.group("mon").lower()):
        found = {"kind": "day", "month": _MONTHS[m.group("mon").lower()],
                 "day": int(m.group("day")), "year": m.group("year"), "yy": None,
                 "end": m.end(), "year_first": True}
    else:
        for pattern in (_MONTH_DAY_RE, _DAY_MONTH_RE):
            m = pattern.match(line, pos)
            if not m:
                continue
            month = _MONTHS.get(m.group("mon").lower())
            cut = None
            if month is None and weekday is not None and pattern is _MONTH_DAY_RE:
                month = cut = _cut_month(m.group("mon"))
            if month:
                groups = m.groupdict()
                found = {"kind": "day", "month": month,
                         "day": int(m.group("day")), "year": groups.get("year"),
                         "yy": groups.get("yy"), "end": m.end()}
                if cut:
                    # Kept only if the weekday then fits (find_page_date checks).
                    found["month_cut"] = m.group("mon")
                break
        if found is None and weekday is not None:
            m = _MONTH_DIGITS_RE.match(line, pos)
            month = _MONTHS.get(m.group("mon").lower()) if m else None
            repaired = _ocr_day_year(month, m.group("digits"), weekday) if month else None
            if repaired:
                found = {"kind": "day", "month": month, "day": repaired[0],
                         "year": repaired[1], "yy": None, "end": m.end(),
                         "ocr_digits": m.group("digits")}
        if found is None:
            m = _MONTH_YEAR_RE.match(line, pos)
            if m and _MONTHS.get(m.group("mon").lower()):
                found = {"kind": "month", "month": _MONTHS[m.group("mon").lower()],
                         "year": m.group("year"), "end": m.end()}
    if found is None:
        return None
    rest = line[found["end"]:]
    # "Jan 1, 1932 - Dec 31, 1932" on a cover is the volume's span, not 1 January
    # (#5557): two dates with written years joined by a dash or "to".
    if found["kind"] in ("day", "month") and found.get("year"):
        sep = _RANGE_SEP_RE.match(rest)
        upto = _date_at(line, found["end"] + sep.end()) if sep and sep.end() else None
        if upto is not None and upto["kind"] in ("day", "month") and upto.get("year"):
            return {"kind": "range", "start": found, "end_date": upto, "end": upto["end"]}
    # A number running on is a ledger row or an amount, not a heading:
    # "15 July 17 Dineen", "October 2.00", "2 May 150 sacks" (with no year).
    # The one exception is a page number after a WRITTEN year, alone to the end
    # of the line ("MAY 13. 1918 12", "SUNDAY, AUGUST 4, 1918 10", #5518): the
    # year closes the date, so what follows cannot be part of it.
    if re.match(r"\s*\d|[.,]\d", rest):
        if found["kind"] == "day" and found.get("year") and _TRAIL_PAGE_NUMBER_RE.match(rest):
            found["trailing_number"] = True
            return found
        return None
    # A yearless date with another date straight after it is a ledger or
    # letter-register row ("Sept.5 Sept24 June26 Newspaper clippings"), not a
    # heading. With a written year it is a heading with a note after it
    # ("SUNDAY, SEPTEMBER 1, 1918 AUGUST 31").
    following = re.match(rf"\s*[,;/|]?\s*(?P<mon>{_WORD})\.?\s*\d", rest, re.IGNORECASE)
    if (following and not found.get("year") and not found.get("yy")
            and _MONTHS.get(following.group("mon").lower())):
        return None
    trail = _TRAIL_WEEKDAY_RE.match(rest)
    if trail and _weekday_of(trail.group("wd")) is not None:
        found["weekday"] = _weekday_of(trail.group("wd"))
        found["end"] += trail.end()
    return found


def _invalid(text: str, reason: str) -> PageDate:
    return PageDate(heading=text, invalid=[{"text": text, "reason": reason}])


#: How far back a yearless date may sit before the page before it and still be
#: the same year: a late entry, a page filed out of place ("July 19th" after
#: "Sept. 10" in the 1915-18 diary is 1916, not 1917). Further back, December
#: to January, is a new year. Measured on the 1915-18 and 1943-45 volumes (#5557).
PAGE_ORDER_BACKSTEP_DAYS = 183


def _year_from_page_order(
    month: int,
    day: int,
    weekday: int | None,
    *,
    previous: int,
    candidates: list[int],
    in_range: list[int],
    page_weekdays: list[tuple[int, int, int]] | tuple,
    to_jdn: Any,
    flags: dict[str, Any],
) -> tuple[int, str]:
    """(year, year_source) for a yearless heading in a volume of several years (#5557).

    WHY page order: the 1915-18 volume's months wrap December to January three
    times, and its yearless headings all took 1915. The year is the one the
    previous dated page carries, the next one when the month goes backwards
    by more than ``PAGE_ORDER_BACKSTEP_DAYS`` (within that, the same year unless
    the weekday chooses the next), kept inside the volume's range.

    A written weekday still decides between that year and the next (a year the
    diarist skipped). It does not pull the page further: when the page's other
    headings fit the page-order year as well as this one fits the other, page
    order holds (1915-18's "Friday March 17" sits between 17 Feb and 17 Apr 1915,
    and its next heading, "Tuesday March 23rd", is 1915's). A weekday that fits
    none of them is flagged, never hidden.
    """
    prev_year, prev_month, prev_day = jdn_to_gregorian(previous)
    back = (prev_month * 31 + prev_day) - (month * 31 + day)
    if back <= 0:
        allowed = [prev_year]
    elif back <= PAGE_ORDER_BACKSTEP_DAYS:
        allowed = [prev_year, prev_year + 1]
    else:
        allowed = [prev_year + 1]
    allowed = [y for y in allowed if y in in_range]
    if not allowed:
        # Past either end of the volume: the nearest year that keeps it inside.
        allowed = [min(in_range, key=lambda y: (abs(y - prev_year - (1 if back > 0 else 0)), y))]
    expected = allowed[0]

    def _fits(y: int, m: int, d: int, w: int) -> bool:
        return 1 <= d <= days_in_month(y, m) and to_jdn(y, m, d) % 7 == w

    if weekday is None:
        return expected, "page_order"
    eligible = [y for y in dict.fromkeys([*allowed, expected + 1]) if y in candidates]
    fits = [y for y in eligible if _fits(y, month, day, weekday)]
    if expected in fits:
        return expected, "page_order"
    if fits:
        other = fits[0]
        votes_other = 1 + sum(_fits(other, m, d, w) for m, d, w in page_weekdays)
        votes_expected = sum(_fits(expected, m, d, w) for m, d, w in page_weekdays)
        if votes_other > votes_expected:
            return other, "weekday"
    flags["weekday_conflict"] = {
        "written": _WEEKDAY_NAMES[weekday],
        "years_that_fit": [y for y in candidates if _fits(y, month, day, weekday)],
        "page_order_year": expected,
    }
    return expected, "page_order"


def _resolve_heading(
    line: str,
    h: dict[str, Any],
    *,
    volume_years: list[int],
    page_year: int | None,
    day_first: bool | None,
    year_start_march: bool,
    assume_julian: bool,
    previous: int | None = None,
    volume_range: tuple[int, int] | None = None,
    page_weekdays: list[tuple[int, int, int]] | tuple = (),
) -> PageDate:
    """Turn a read heading into a dated page, or a recorded refusal.

    ``previous`` is the JDN of the page before this one in the volume's reading
    order that has a date, ``volume_range`` the volume's first and last days
    when its name gives them, ``page_weekdays`` the (month, day, weekday) of the
    page's other yearless headings: all three only settle a yearless heading's
    year in a volume of several years (#5557).
    """
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

    if h["kind"] == "range":
        # A written span, "Jan 1, 1932 - Dec 31, 1932" (a cover, #5557): from the
        # first day of its start to the last day of its end, never the 1st alone.
        ends = []
        for part, last in ((h["start"], False), (h["end_date"], True)):
            year = int(part["year"])
            if (problem := _check_year(year)) is not None:
                return _invalid(line, problem)
            if part["kind"] == "month":
                ends.append(_month_range_jdn(year, part["month"], calendar)[1 if last else 0])
                continue
            if not 1 <= part["day"] <= days_in_month(year, part["month"], julian_calendar=assume_julian):
                return _invalid(line, f"{_MONTH_NAMES[part['month'] - 1]} has no day {part['day']}")
            ends.append(to_jdn(year, part["month"], part["day"]))
        if ends[1] < ends[0]:
            return _invalid(line, "the range ends before it starts")
        date = _make(text, ends[0], ends[1], calendar=calendar, precision="range",
                     confidence=0.8, display=text)
        date.meta.update(heading=line, year_source="written", year_inferred=False)
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
        elif a == b:
            day, month, order = a, b, "day/month"  # 5/5: both readings are one date
        elif day_first is None:
            # No language says which: record both readings, date nothing.
            readings = []
            for first in (True, False):
                reading = _resolve_heading(
                    line, h, volume_years=volume_years, page_year=page_year,
                    day_first=first, year_start_march=year_start_march,
                    assume_julian=assume_julian,
                )
                readings.append({
                    "order": "day/month" if first else "month/day",
                    "date": reading.date.meta["converted_gregorian_iso"] if reading.date else None,
                    "invalid": reading.invalid[0]["reason"] if reading.invalid else None,
                })
            if not any(r["date"] for r in readings):
                return _invalid(line, readings[0]["invalid"] or "not a real date")
            return PageDate(heading=line, ambiguous=[{"text": line, "readings": readings}])
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
        if year not in volume_years:
            # "11/16/23" in the 1943-45 volume (#5557): a two-digit year is read
            # by its volume, so one that names none of the volume's years is a
            # slip or another matter's date, not 1923. Refused and recorded.
            return _invalid(line, f"the two-digit year {yy} is none of the volume's years "
                                  f"{volume_years[0]}-{volume_years[-1]}")
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

        def _in_range(y: int) -> bool:
            return volume_range is None or volume_range[0] <= to_jdn(y, month, day) <= volume_range[1]

        # The volume's full date range, not only its years (#5557): a volume that
        # begins 17 October 1943 never gives "Feb 27" the year 1943. When no year
        # puts the date inside the range, every year stays a candidate.
        in_range = [y for y in candidates if _in_range(y)] or candidates
        if in_range and in_range[0] != year:
            year = in_range[0]
        if previous is not None and len(volume_years) > 1 and in_range:
            year, year_source = _year_from_page_order(
                month, day, weekday, previous=previous, candidates=candidates,
                in_range=in_range, page_weekdays=page_weekdays, to_jdn=to_jdn, flags=flags)
        elif weekday is not None:
            fits = ([y for y in in_range if to_jdn(y, month, day) % 7 == weekday]
                    or [y for y in candidates if to_jdn(y, month, day) % 7 == weekday])
            if fits:
                year, year_source = fits[0], "weekday" if len(candidates) > 1 else "volume"
                if len(fits) > 1:
                    flags["year_ambiguous"] = fits
            else:
                flags["weekday_conflict"] = {"written": _WEEKDAY_NAMES[weekday],
                                             "years_that_fit": []}
        elif len(in_range) > 1:
            flags["year_ambiguous"] = in_range
        if not _in_range(year):
            flags["outside_volume_range"] = True
    elif weekday is not None and to_jdn(year, month, day) % 7 != weekday:
        fits = [y for y in volume_years
                if day <= days_in_month(y, month, julian_calendar=assume_julian)
                and to_jdn(y, month, day) % 7 == weekday] if volume_years else []
        if year_source == "written" and year not in volume_years and len(fits) == 1:
            # The 1919 rule (ruled by the maintainer, #5518): when the written
            # weekday AND the volume's own year agree against the written year,
            # they win. Diarists write last year's year early in a new volume.
            # The written year is kept beside the date and flagged, never dropped.
            flags["year_overruled"] = {"written": year, "weekday": _WEEKDAY_NAMES[weekday],
                                       "volume_years": [volume_years[0], volume_years[-1]],
                                       "chosen": fits[0]}
            flags["written_year"] = year
            year, year_source = fits[0], "weekday_and_volume"
        else:
            flags["weekday_conflict"] = {"written": _WEEKDAY_NAMES[weekday],
                                         "date_is": _WEEKDAY_NAMES[to_jdn(year, month, day) % 7],
                                         "years_that_fit": fits}
    if year_source == "written":
        _volume_flag(year)

    jdn = to_jdn(year, month, day)
    inferred = year_source in ("volume", "weekday", "page", "weekday_and_volume", "page_order")
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
    day_first: bool | None = None,
    year_start_march: bool = False,
    assume_julian: bool = False,
    max_lines: int = HEADING_LINES,
    previous: int | None = None,
    volume_range: tuple[int, int] | None = None,
    other_years_are_mentions: bool = True,
) -> PageDate:
    """The date a page's own heading gives it, with what was refused and why.

    ``volume_years`` are the years the page's volume or folder covers (see
    ``years_from_name``): a yearless heading takes one, marked inferred.
    ``previous`` (the JDN of the dated page before this one in the volume's
    reading order) and ``volume_range`` (the volume's first and last days)
    settle that year in a volume of several years (``_year_from_page_order``).
    ``other_years_are_mentions`` (on for dating a page, off for checking a
    supplied date against its heading, where a heading of another year IS the
    conflict to report): a written date or year line more than a year from the
    volume's is a mention, not the page's date (#5557).
    """
    all_lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    lines = all_lines[:max_lines]
    if not lines or is_explicitly_undated(lines[0]):
        return PageDate()
    for index, line in enumerate(lines[:3]):
        marker = _NON_ENTRY_RE.match(line)
        if marker:
            return PageDate(non_entry=re.sub(r"\s+", " ", marker.group(1)).upper())
        if _PRINTED_MEMORANDA_RE.match(line):
            return PageDate(non_entry="MEMORANDA")
        if _CASH_COLUMNS_RE.match(line) and not any(
                (above_h := _heading_date(above)) is not None and above_h.get("year")
                for above in lines[:index]):
            return PageDate(non_entry="CASH ACCOUNT")
    years = sorted(set(volume_years or []))
    page_year: int | None = None
    fallback: tuple[str, dict[str, Any]] | None = None
    common = {"day_first": day_first, "year_start_march": year_start_march,
              "assume_julian": assume_julian, "previous": previous, "volume_range": volume_range}

    def _other_weekdays(after: int) -> list[tuple[int, int, int]]:
        """The page's other yearless weekday headings below ``after``: (month, day, weekday)."""
        out = []
        for below in lines[after + 1:]:
            other = _heading_date(below)
            if (other is not None and other["kind"] == "day" and other.get("weekday") is not None
                    and not other.get("year") and not other.get("yy")):
                out.append((other["month"], other["day"], other["weekday"]))
        return out

    for index, line in enumerate(lines):
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
        if h.get("trailing_number") and not _weekday_fits(h, years, assume_julian):
            # "THURSDAY, APRIL 5, 1918 24": a number after the year is only a
            # page number when the rest of the heading holds together; here the
            # weekday fits neither the year nor the volume, so the line is
            # garbled and the next heading dates the page.
            continue
        if h.get("month_cut") and not _weekday_fits(h, years, assume_julian):
            # "FRIDAY, OCTOBE 3" (#5557): a month name cut short is read only when
            # the weekday written before it confirms the date.
            continue
        if other_years_are_mentions and _mentions_another_year(h, years):
            # "August 5, 1926. - NCM - Pauline Williams. Cancelled." in the 1929
            # diary (#5557): a full date with no weekday, in a year more than one
            # away from the volume's, is a memo's date, not the page's.
            continue
        if _is_margin_label(h):
            # "Mar. 23" in the margin, then "Saturday, March 23, 1918" (#5518):
            # the full heading of the same day wins; the label carries no year
            # or weekday, so a volume year would otherwise be guessed for it.
            # A full heading (weekday and year) a day or two away wins too:
            # "Feb. 9" over "SATURDAY, FEBRUARY 8 1918" labels the page's next
            # entry, not its first (#5557).
            for offset, below in enumerate(lines[index + 1:index + 3], start=index + 1):
                full = _heading_date(below)
                if full is None or full["kind"] != "day" or _is_margin_label(full):
                    continue
                apart = abs((full["month"] * 31 + full["day"]) - (h["month"] * 31 + h["day"]))
                label_alone = len(line) <= len(h["text"]) + 2
                if apart == 0 or (apart <= 2 and label_alone and full.get("weekday") is not None
                                  and full.get("year")):
                    line, h, index = below, full, offset
                    break
        return _resolve_heading(line, h, volume_years=years, page_year=page_year,
                                page_weekdays=_other_weekdays(index), **common)
    # No heading near the top: a diary written as running prose dates its
    # entries further down ("Sunday February 14th - Ran aground", line 25 of a
    # 1915 page, #5518). Only a line that LEADS with a weekday and a date counts
    # there; a bare "July 9" deep in a page is a mention or a ledger row.
    for line in all_lines[max_lines:]:
        h = _heading_date(line)
        if (h is not None and h["kind"] == "day" and h.get("weekday") is not None
                and not h.get("closing") and not h.get("month_cut")):
            return _resolve_heading(line, h, volume_years=years, page_year=page_year, **common)
    if fallback is not None:
        first = int(fallback[1]["y1"])
        if other_years_are_mentions and years and not years[0] - 1 <= first <= years[-1] + 1:
            # "Arrived here March 10, / 1924." in the 1927 diary, "reappointed
            # Gerente Dec. 1937." in the 1939 one (#5557): a year line more than
            # a year from the volume's is a mention; with no heading on the page
            # it dates nothing. (The 1919 volume's printed "STANDARD DIARY 1918"
            # is the year before, as its "1918" headings are, and keeps it.)
            return PageDate()
        return _resolve_heading(fallback[0], fallback[1], volume_years=years,
                                page_year=None, **common)
    return PageDate()


def _mentions_another_year(h: dict[str, Any], years: list[int]) -> bool:
    """A written date with no weekday, its year more than one from the volume's (#5557).

    The 1919 volume's "1918"s stay headings (the year before the volume, the
    1919 rule); a memo's "August 5, 1926" in the 1929 diary does not.
    """
    if not years or h["kind"] not in ("day", "month") or h.get("weekday") is not None:
        return False
    if not h.get("year"):
        return False
    year = int(h["year"])
    return year < years[0] - 1 or year > years[-1] + 1


def extract_date_from_text(
    text: str,
    *,
    year_start_march: bool = False,
    assume_julian: bool = False,
    max_chars: int = 4000,
    volume_years: list[int] | tuple[int, ...] | None = None,
    day_first: bool | None = None,
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
