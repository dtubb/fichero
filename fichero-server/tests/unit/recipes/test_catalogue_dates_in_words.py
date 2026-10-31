"""catalogue.export.dates-parser-reads-words (#6282, #6270): days and months written in Spanish words are read with no model."""
from __future__ import annotations

import pytest

from fichero_server.recipes.catalogue_step import parse_fields


def _norm(dates: str) -> str | None:
    return parse_fields(f"Dates: {dates}").get("catalogue_date_normalised")


@pytest.mark.parametrize("dates,edtf", [
    ("a los ocho días del mes de mayo de mil novecientos nueve", "1909-05-08"),
    ("primero de enero de mil ochocientos noventa", "1890-01-01"),
    ("a los veintiún días del mes de abril de 1910", "1910-04-21"),
    ("a los veinte y cinco días del mes de Mayo de mil novecientos nueve", "1909-05-25"),
    ("treinta y uno de diciembre de mil ochocientos noventa y nueve", "1899-12-31"),
    ("el 1° de mayo de 1910", "1910-05-01"),
    ("mayo de mil novecientos nueve", "1909-05"),
    ("dos de enero de dos mil veinticuatro", "2024-01-02"),
])
def test_days_months_and_years_in_words(dates, edtf):
    assert _norm(dates) == edtf


@pytest.mark.parametrize("dates,edtf", [
    ("a mediados de mayo de 1910", "1910-05~"),
    ("a mediados de 1910", "1910~"),
])
def test_approximately_is_marked(dates, edtf):
    assert _norm(dates) == edtf


def test_a_range_mixing_words_and_digits_keeps_each_precision():
    got = _norm("a los veinte y cinco días del mes de Mayo de mil novecientos nueve - 3 de junio de 1910")
    assert got == "1909-05-25/1910-06-03"


def test_a_day_with_no_year_is_not_guessed_and_money_is_still_no_year():
    assert _norm("primero de enero") is None
    assert _norm("mil pesos, 1906") == "1906"
