"""The shipped model cards (`source.model.card-id`) and what the rules make of them for real cases.

Why it matters: these cards are what setup reasons from on day one. A malformed id breaks every
recipe that names it; a card whose runtime is not in the build (Tesseract today) must not be
proposed; and on the 8 GB Air a 7 GB model must not be chosen, or the first run swaps the Mac to a
standstill (2026-10-01).
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, assemble
from fichero_server.recipes.cards import CARD_ID, seed_cards


def _models(recipe):
    return {s["job"]: s.get("model") for s in recipe["steps"]}


def test_every_seed_card_has_a_card_id():
    cards = seed_cards()
    assert cards and all(CARD_ID.match(c.id) for c in cards)


def test_a_runtime_not_in_this_build_is_not_a_candidate():
    assert not any(c.id.startswith("tesseract:") for c in seed_cards())


def test_spanish_letters_on_a_16gb_mac():
    m = _models(assemble(Answers("search", frozenset({"es"}), frozenset({"Latn"}), mac_memory_gb=16), list(seed_cards())))
    assert m["find-lines"]["kraken"] == "blla"
    assert m["read-a-line"] == {"zenodo": "10.5281/zenodo.21788410"}   # the one with a published CER
    assert m["correct"]["hf"] == "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"


def test_on_the_8gb_air_the_7gb_corrector_is_not_chosen_and_the_gap_is_named():
    recipe = assemble(Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), mac_memory_gb=8), list(seed_cards()))
    correct = next(s for s in recipe["steps"] if s["job"] == "correct")
    assert "gap" in correct and "memory" in correct["gap"]
