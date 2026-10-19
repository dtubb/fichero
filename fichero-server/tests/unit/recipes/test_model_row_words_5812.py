"""A model row says Available / Downloaded / Download and carries a short name (`source.find.model-row-words`, #5812)."""
from __future__ import annotations

from fichero_server.recipes.discovery import candidate_availability, short_name, shipped_words
from tests.unit.recipes.test_one_candidate_source_5808 import card


def test_a_built_in_model_is_available_never_ships_with_fichero():
    built_in = card("apple", pin={"builtin": "apple-vision"})
    assert candidate_availability(built_in) == ("ships", "Available")


def test_the_short_name_is_the_cards_own_else_the_first_clause_clipped_at_a_word():
    from dataclasses import replace

    blla = replace(card("kraken-blla", pin={"kraken": "blla"}),
                   note="Kraken's built-in line and region finder (blla); ships inside the app.",
                   short_name="Kraken line finder (blla)")
    assert short_name(blla) == "Kraken line finder (blla)"
    plain = replace(card("x", pin={"hf": "a/b"}), note="McCATMuS, general Latin-script recognition, 16th-21st century.")
    assert short_name(plain) == "McCATMuS"
    long = replace(card("y", pin={"hf": "c/d"}), note="A very long single clause name that runs on and on past any row width")
    assert len(short_name(long)) <= 40 and not short_name(long).endswith(" ") and long.note.startswith(short_name(long))


def test_no_words_say_ships_with_fichero():
    assert "ships with" not in shipped_words([card("a", pin={"builtin": "apple-vision"})]).lower()
    assert "Nothing" in shipped_words([]) and "ships" not in shipped_words([]).lower()
