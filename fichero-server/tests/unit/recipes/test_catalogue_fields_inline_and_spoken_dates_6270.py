"""The Catalogue answer's fields land in their own attributes wherever the model wrote them, and the year range agrees with
the Dates text (#6270): GHC_B12's access points sat inside Condition, and 1918 stood as the start of "... mil novecientos seis - ... 1918"."""
from __future__ import annotations

from fichero_server.recipes.catalogue_step import parse_fields

INLINE = ('Title: Liquidaciones.\nDates: cuatro al cinco de Diciembre de mil novecientos seis – Diciembre 5 de 1918.\n'
          'Condition: tachadura anotada "3 = no val" en liquidación de mayo de 1918. Access points: Juana Matea Rivas; '
          'Juan Antonio Rivas; Hacienda Santa Rosa.\nScope and content: Cuentas.')


def test_access_points_written_inline_after_condition_are_their_own_field():
    got = parse_fields(INLINE)
    assert got["catalogue_access_points"] == ["Juana Matea Rivas", "Juan Antonio Rivas", "Hacienda Santa Rosa"]
    assert got["catalogue_condition"] == 'tachadura anotada "3 = no val" en liquidación de mayo de 1918.'


def test_a_year_in_spanish_words_is_the_start():
    got = parse_fields(INLINE)
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == ("1906", "1918")


def test_a_range_whose_first_year_cannot_be_read_has_no_numeric_dates():
    got = parse_fields("Dates: cuatro de abril de tal – 5 de mayo de 1918.")
    assert "catalogue_date_start" not in got and "catalogue_date_end" not in got


def test_digit_ranges_and_a_single_year_still_work():
    assert parse_fields("Dates: 1850-60.")["catalogue_date_end"] == "1860"
    one = parse_fields("Dates: 1776.")
    assert (one["catalogue_date_start"], one["catalogue_date_end"]) == ("1776", "1776")


def test_a_field_stops_at_the_blank_line_and_prose_after_it_adds_no_dates():
    got = parse_fields("Dates: 1906\n\nThe folder holds letters of 1850 and 1990.")
    assert got["catalogue_dates"] == "1906"
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == ("1906", "1906")


def test_spoken_years_stop_at_the_years_last_word_and_money_is_no_year():
    got = parse_fields("Dates: 3 de abril de mil novecientos seis - dos de mayo de mil novecientos siete")
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == ("1906", "1907")
    got = parse_fields("Dates: mil pesos, 1906")
    assert (got["catalogue_date_start"], got["catalogue_date_end"]) == ("1906", "1906")
