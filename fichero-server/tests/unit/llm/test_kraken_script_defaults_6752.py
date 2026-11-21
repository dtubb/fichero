"""#6752: the line finder's base and network height per script, as measured (kraken-scripts-eval 3.1/3.2/7)."""
from __future__ import annotations

import pytest

from fichero_server.llm.kraken_script_defaults import DEFAULT, segmenter_defaults


@pytest.mark.parametrize("script", ["Hebr", "Arab", "Deva"])
def test_large_right_to_left_and_devanagari_scripts_use_the_2026_base_at_1200(script):
    got = segmenter_defaults(script)
    assert (got.base, got.height) == ("2026", 1200)


@pytest.mark.parametrize("script", ["Syrc", "Syre", "Syrj", "Syrn", "Aran"])
def test_syriac_and_nastaliq_keep_the_bundled_base_at_1200(script):
    got = segmenter_defaults(script)
    assert (got.base, got.height) == ("bundled", 1200)


def test_palm_leaf_strips_get_a_small_height():
    assert segmenter_defaults("Newa").height == 300


@pytest.mark.parametrize("script", ["Latn", "Grek", None, "Zzzz"])
def test_latin_and_unmeasured_scripts_keep_the_bundled_base_at_1800(script):
    assert segmenter_defaults(script) == DEFAULT == segmenter_defaults("Latn")
    assert (DEFAULT.base, DEFAULT.height) == ("bundled", 1800)
