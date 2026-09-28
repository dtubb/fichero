"""A place over time: which of its geometries held at a date (maps D7, #5120;
`source.geo.geometry-over-time`).

A place's geometries are its dated `EvidentialPlace` rows -- a span (Pleiades's -330..640) or a point
in time (a Wikidata position `P585` 2019: start == end). As of a date the answer is EVERY geometry
valid then (rivals stay rivals, each with its source), or none with the reason -- never the nearest,
which would be a guess presented as a fact. An undated geometry is listed apart: valid, time unknown.

Years are compared at year granularity on the astronomical count (1 BC = 0), each span converted
from the numbering it names (`EvidentialDateRange.numbering`); the years themselves are stored as the
source wrote them. The full date model (`source.date.*`, #4936) is not this: a span keeps its wording.
"""

from __future__ import annotations

import re

_YEAR = re.compile(r"^\s*([+-]?)0*(\d{1,6})")


def astronomical_year(value, numbering: str | None = None) -> int | None:
    """The year of `value` ("-330", "1700", "+2019-00-00T00:00:00Z", "1831-06-01") on the
    astronomical count, or None when it states none."""
    if value is None:
        return None
    match = _YEAR.match(str(value))
    if not match:
        return None
    year = int(match.group(1) + match.group(2))
    if numbering == "historical" and year < 0:
        year += 1          # historical numbering has no year 0: 1 BC is astronomical 0
    return year


def is_dated(span) -> bool:
    return span is not None and (astronomical_year(span.start, span.numbering) is not None
                                 or astronomical_year(span.end, span.numbering) is not None)


def valid_at(span, year: int) -> bool:
    """Whether `span` holds in `year`. A bound left out is open only when the span says so
    (`open_start` / `open_end`); otherwise the other bound stands for it -- a point in time."""
    start = astronomical_year(span.start, span.numbering)
    end = astronomical_year(span.end, span.numbering)
    low = start if start is not None else (None if span.open_start else end)
    high = end if end is not None else (None if span.open_end else start)
    return (low is None or low <= year) and (high is None or year <= high)


def geometries_as_of(entity, as_of: str) -> dict:
    """{geometries, undated, reason} for the entity's place evidence as of `as_of` (an ISO 8601
    year or date, astronomical count). `reason` is None when something is valid."""
    year = astronomical_year(as_of, "astronomical")
    if year is None:
        raise ValueError(f"as_of {as_of!r} is not a year or an ISO 8601 date")
    places = list(entity.place_values or [])
    valid = [place for place in places if is_dated(place.when) and valid_at(place.when, year)]
    undated = [place for place in places if not is_dated(place.when)]
    return {"geometries": valid, "undated": undated,
            "reason": None if valid else f"none valid in {as_of}"}
