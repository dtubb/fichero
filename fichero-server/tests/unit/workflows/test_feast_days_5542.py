"""`source.date.feast-days` (#5542): a date written as a feast is worked out, with its reasoning.

WHY: the topic says Fichero turns "dia de San Juan de 1791" into an exact date; no code did, so such a date stayed
words and sorted nowhere. Checked against dates the almanac gives: Easter 1791 fell on 24 April (Gregorian), Easter
2024 on 31 March (Gregorian) and 5 May (Julian church, as the Gregorian count).
"""
from __future__ import annotations

import pytest
from fichero_server.feast_days import fold, table
from fichero_server.histdate import jdn_to_gregorian, parse_historical_date


def _day(text: str, **kw):
    parsed = parse_historical_date(text, **kw)
    return parsed, (jdn_to_gregorian(parsed.jdn) if parsed else None)


def test_a_movable_feast_is_days_after_easter_in_the_calendar_of_the_source_5542():
    parsed, day = _day("Pascua de 1791")
    assert day == (1791, 4, 24) and parsed.jdn == parsed.jdn_end and parsed.meta["precision"] == "day"
    assert _day("Pentecostés de 1791")[1] == (1791, 6, 12)  # Easter + 49
    assert _day("Good Friday 1791")[1] == (1791, 4, 22)
    assert _day("Easter 2024")[1] == (2024, 3, 31)
    julian, day = _day("Easter 2024", assume_julian=True)
    assert day == (2024, 5, 5) and julian.meta["calendar_system"] == "julian"


def test_a_fixed_feast_is_its_day_and_keeps_its_reasoning_5542():
    parsed, day = _day("día de San Miguel de 1791")
    assert day == (1791, 9, 29) and parsed.meta["converted_gregorian_iso"] == "1791-09-29"
    assert "fixed feast" in parsed.meta["reasoning"] and "09-29" in parsed.meta["reasoning"]
    assert parsed.meta["feast"] == "michaelmas" and "alternatives" not in parsed.meta
    julian, day = _day("Michaelmas 1650", assume_julian=True)  # 29 September Old Style = 9 October New Style
    assert day == (1650, 10, 9) and julian.meta["calendar_system"] == "julian"
    assert "Easter" in _day("Whitsun 1700")[0].meta["reasoning"]


def test_a_name_that_can_mean_two_feasts_names_the_other_and_is_less_sure_5542():
    baptist, day = _day("el día de San Juan de 1791")
    assert day == (1791, 6, 24) and baptist.meta["alternatives"] == ["st-john-evangelist"]
    evangelist = parse_historical_date("San Juan Evangelista de 1791")
    assert jdn_to_gregorian(evangelist.jdn) == (1791, 12, 27) and "alternatives" in evangelist.meta
    assert baptist.meta["confidence"] < _day("Pascua de 1791")[0].meta["confidence"]
    assert _day("San Miguel 1791")[0].meta["confidence"] > baptist.meta["confidence"]


@pytest.mark.parametrize("text,expected", [
    ("the feast of St John the Baptist 1791", (1791, 6, 24)),
    ("Johannistag 1791", (1791, 6, 24)),
    ("Ostern 1791", (1791, 4, 24)),
    ("in die Pentecostes anno 1791", (1791, 6, 12)),
    ("Todos los Santos de 1791", (1791, 11, 1)),
    ("St. Martin's Day 1791", (1791, 11, 11)),
    ("Weihnachten 1791", (1791, 12, 25)),
])
def test_a_name_in_another_language_is_a_row_of_the_table_5542(text, expected):
    parsed = parse_historical_date(text)
    assert parsed is not None and jdn_to_gregorian(parsed.jdn) == expected


def test_a_feast_the_table_does_not_hold_gives_no_date_5542():
    assert parse_historical_date("día de San Fulano de 1791") is None
    assert parse_historical_date("Pascua") is None  # no year: not a day
    assert parse_historical_date("San Juan") is None


def test_the_table_is_sound_5542():
    t = table()
    assert len(t["feasts"]) >= 30 and fold("St. Martin's Day") == "st martins day"
    assert all(t["by_name"][fold(n)] == feast for feast, row in t["feasts"].items() for n in row["names"])
