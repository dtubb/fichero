"""A number saved as text (a page count, a memory figure, a cap) in a Set Up answer is read as the
number it spells, or refused in words naming the field, never a `'>=' not supported between 'str'
and 'int'` in the Start plan (#6298)."""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import as_number


def test_a_page_count_saved_as_text_is_read_as_a_number():
    assert as_number("92", "pages", whole=True) == 92
    # the places a plan compares it: the training threshold and the cloud-offer guard
    assert as_number("5000", "pages", whole=True) >= 5000
    assert as_number("5001", "pages", whole=True) > 5000


def test_a_memory_figure_saved_as_text_is_read_as_a_number():
    assert as_number("16", "mac_memory_gb") == 16.0
    assert as_number("8.5", "mac_memory_gb") == 8.5


@pytest.mark.parametrize(
    "bad", ["lots", "", "92.7", 92.5, "inf", float("inf"), float("nan"), True]
)
def test_a_page_count_that_is_not_a_whole_number_is_said_in_words(bad):
    with pytest.raises(ValueError, match="pages"):
        as_number(bad, "pages", whole=True)


@pytest.mark.parametrize(
    "bad", ["lots", "", "inf", float("inf"), float("nan"), True]
)
def test_a_memory_figure_that_is_not_a_number_is_said_in_words(bad):
    with pytest.raises(ValueError, match="mac_memory_gb"):
        as_number(bad, "mac_memory_gb")


def test_a_whole_number_written_as_a_float_is_that_number():
    assert as_number("16.0", "mac_memory_gb") == 16.0
    assert as_number(16.0, "mac_memory_gb") == 16.0
    assert as_number("92.0", "pages", whole=True) == 92


@pytest.mark.parametrize("zero", [0, 0.0, "0"])
def test_zero_is_a_valid_number_however_it_is_written(zero):
    assert as_number(zero, "pages", whole=True) == 0
    assert as_number(zero, "mac_memory_gb") == 0.0


def test_none_returns_none():
    assert as_number(None, "pages", whole=True) is None
    assert as_number(None, "mac_memory_gb") is None