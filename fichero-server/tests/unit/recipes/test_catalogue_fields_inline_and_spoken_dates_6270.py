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


def _span(dates: str) -> tuple[str, str]:
    got = parse_fields(f"Dates: {dates}")
    return got["catalogue_date_start"], got["catalogue_date_end"]


def test_a_number_before_de_month_is_a_day_not_a_short_end_year():
    assert _span("1913 - 19 de febrero de 1918") == ("1913", "1918")


def test_spanish_thousands_punctuation_is_read_as_a_year():
    assert _span("1.909 - 1.918") == ("1909", "1918")


def test_a_year_in_digits_and_words_gives_one_year():
    assert _span("1.909 – febrero de mil novecientos nueve") == ("1909", "1909")
    assert _span("mil ochocientos noventa") == ("1890", "1890")


def test_a_three_digit_year_with_the_one_dropped_ends_the_range_only_beside_a_full_year():
    assert _span("1906 – del 914") == ("1906", "1914")
    assert _span("1850, folio 914") == ("1850", "1850")  # 1914 is 64 years from 1850: not a year


def _norm(dates: str) -> str:
    return parse_fields(f"Dates: {dates}")["catalogue_date_normalised"]


def test_normalised_date_of_a_year_then_a_day():
    got = parse_fields("Dates: 1913 - 19 de febrero de 1918")
    assert got["catalogue_date_normalised"] == "1913/1918-02-19"
    assert got["catalogue_dates"] == "1913 - 19 de febrero de 1918"  # the original text stays


def test_normalised_date_of_spanish_thousands_years():
    assert _norm("1.909 - 1.918") == "1909/1918"


def test_normalised_date_of_one_year_written_twice_is_one_date():
    assert _norm("1.909 – febrero de mil novecientos nueve") == "1909"


def test_normalised_date_of_a_dropped_one_year():
    assert _norm("1906 – del 914") == "1906/1914"


def test_normalised_date_keeps_month_precision_and_marks_approximate_and_uncertain():
    assert _norm("marzo de 1906 - 19 de febrero de 1918") == "1906-03/1918-02-19"
    assert _norm("c. 1850") == "1850~"
    assert _norm("1906? - 1918") == "1906?/1918"


def test_normalised_date_keeps_a_day_written_after_the_month():
    assert _norm("Mayo 8 de 1906 – Diciembre 5 de 1918") == "1906-05-08/1918-12-05"
    assert _norm("8 de mayo de 1906 – 5 de diciembre de 1918") == "1906-05-08/1918-12-05"


def test_amounts_with_a_dot_are_not_years():
    assert _span("1906-1918; 1.500 pesos") == ("1906", "1918")
    assert _span("2.000 pesos, 1910") == ("1910", "1910")
    assert _span("1906 - 1910, 1.200 folios") == ("1906", "1910")
    assert _span("1906 - 1910, 1.900 pesos") == ("1906", "1910")
    assert _span("1906 - 1910, $ 1.900") == ("1906", "1910")
    assert _norm("1906 - 1910, 1.200 folios") == "1906/1910"  # the normalised years are the span's


def test_a_three_digit_number_in_a_folio_or_money_phrase_is_not_a_year():
    assert _span("1906 - 1910 (folios 1-914)") == ("1906", "1910")
    assert _span("1906 - 1910 (folios 1 a 914)") == ("1906", "1910")
    assert _span("885 pesos 1890") == ("1890", "1890")
    assert _span("1906 - 1910, de 914 pesos") == ("1906", "1910")


def test_a_reversed_range_is_ordered_in_the_interval():
    assert _norm("1918 - 1906") == "1906/1918"


def test_al_joins_two_days_of_one_month():
    assert _span("19 al 25 de mayo de 1910") == ("1910", "1910")
    assert _norm("19 al 25 de mayo de 1910") == "1910-05-19/1910-05-25"


def test_approximate_and_uncertain_is_percent():
    assert _norm("ca. 1906?") == "1906%"
    assert _norm("ca. 1906") == "1906~"
