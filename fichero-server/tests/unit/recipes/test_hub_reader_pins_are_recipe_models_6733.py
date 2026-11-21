"""`source.find.one-candidate-source` (#6733 item 3): the pins discovery builds for a Hugging Face Kraken or TrOCR
reader are model shapes a recipe accepts, so a candidate a page lists can be a step's reader."""
from __future__ import annotations

import pytest

from fichero_server.recipes.recipe import _check_model


@pytest.mark.parametrize("pin", [{"kraken_hf": "dh-unibe/kraken-x"},
                                 {"kraken_hf": "dh-unibe/kraken-x", "revision": "abc123"},
                                 {"trocr": "microsoft/trocr-base-handwritten"}])
def test_a_hub_reader_pin_is_a_known_model_shape(pin):
    out: list[str] = []
    _check_model("steps.0.model", pin, out)
    assert out == []


def test_an_unknown_shape_is_still_refused():
    out: list[str] = []
    _check_model("steps.0.model", {"kraken_hf": "a/b", "trocr": "c/d"}, out)
    assert len(out) == 1
