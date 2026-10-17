"""`source.recipe.unstated-period-is-offered-not-chosen` (#5714), `source.recipe.apple-vision-is-for-modern-writing` (#5715).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. The rule names no date and no script: the
cases below are built from the shipped cards and from synthetic ones, so a Chinese or an Arabic project is the same code.
"""
from __future__ import annotations

from dataclasses import replace

from fichero_server.recipes.assemble import Answers, _choose, _refusal
from fichero_server.recipes.cards import all_seed_cards

APPLE = "apple:vision/recognize-text@os"
MCCATMUS = "kraken:zenodo/10.5281/zenodo.13788177@unpinned"


def _cards():
    return {c.id: c for c in all_seed_cards()}


def _a(**kw):
    base = {"languages": frozenset({"es"}), "scripts": frozenset({"Latn"}), "materials": ("handwriting",),
            "mac_memory_gb": 64, "period": "16th century"}
    return Answers(**{**base, **kw})


def test_apple_vision_states_a_modern_period_5715():
    assert _cards()[APPLE].period == (1900, 2100)


def test_apple_vision_is_refused_for_a_sixteenth_century_hand_and_named_5715():
    refused = _refusal("read-a-page", _cards()[APPLE], _a(), "handwriting")
    assert refused is not None and refused[0] == "no-reader-for-period", refused
    assert "1900" in refused[1] and "2100" in refused[1]


def test_apple_vision_is_not_refused_for_a_modern_hand_5715():
    assert _refusal("read-a-page", _cards()[APPLE], _a(period="1950"), "handwriting") is None


def test_apple_vision_reads_print_of_any_period_5715():
    a = _a(materials=("print",))
    assert _refusal("read-a-page", _cards()[APPLE], a, "print") is None


def test_a_card_with_no_period_is_never_the_rules_choice_for_old_handwriting_5714():
    unstated = replace(_cards()[APPLE], id="x:unstated", period=None, installed=True)
    other = replace(unstated, id="x:other")
    choice = _choose("read-a-page", [unstated, other], _a(), "handwriting")
    assert choice.card is None and choice.gap, choice


def test_the_period_matched_reader_is_chosen_over_an_unstated_one_5714():
    cards = _cards()
    unstated = replace(cards[APPLE], id="x:unstated", period=None, installed=True, jobs=frozenset({"read-a-line"}))
    matched = replace(cards[MCCATMUS], jobs=frozenset({"read-a-line"}))
    choice = _choose("read-a-line", [unstated, matched], _a(), "handwriting")
    assert choice.card is not None and choice.card.id == MCCATMUS


def test_an_unstated_reader_is_still_chosen_when_the_project_states_no_period_5714():
    unstated = replace(_cards()[APPLE], id="x:unstated", period=None)
    choice = _choose("read-a-page", [unstated], _a(period=""), "handwriting")
    assert choice.card is not None and choice.card.id == "x:unstated"


def test_an_unstated_reader_is_still_chosen_for_print_5714():
    unstated = replace(_cards()[APPLE], id="x:unstated", period=None)
    choice = _choose("read-a-page", [unstated], _a(materials=("print",)), "print")
    assert choice.card is not None


def test_apple_vision_reads_other_scripts_printed_only_5715():
    han = _a(scripts=frozenset({"Hani"}), languages=frozenset({"zh"}), period="1950")
    assert _refusal("read-a-page", _cards()[APPLE], han, "handwriting")[0] == "no-reader-for-material"
    assert _refusal("read-a-page", _cards()[APPLE], replace(han, materials=("print",)), "print") is None


def test_the_bakeoff_names_a_reader_made_for_another_period_with_why_5715(monkeypatch):
    """`source.recipe.apple-vision-is-for-modern-writing`: named once with the reason, never scored, never dropped."""
    from fichero_server.recipes import bakeoff
    from fichero_server.training import evaluation

    monkeypatch.setattr(evaluation, "apple_vision_here", lambda: True)
    old = {c["card"]: c for c in bakeoff.candidates(_a(), list(all_seed_cards()), volume=100)}
    assert APPLE in old, "a reader made for another period is named, not silently dropped"
    assert old[APPLE]["not_scored"] and "1900" in old[APPLE]["not_scored"], old[APPLE]["not_scored"]
    modern = {c["card"]: c for c in bakeoff.candidates(_a(period="1950"), list(all_seed_cards()), volume=100)}
    assert modern[APPLE]["not_scored"] is None
