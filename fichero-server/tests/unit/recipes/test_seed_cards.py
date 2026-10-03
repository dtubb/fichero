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
    # PP-OCRv6, the reader with a published CER; fetched from Kraken's repository by its DOI.
    assert m["read-a-line"] == {"zenodo": "10.5281/zenodo.21788410"}
    assert m["correct"]["hf"] == "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"


def test_on_the_8gb_air_the_7gb_corrector_is_not_chosen_and_the_gap_is_named():
    recipe = assemble(Answers("transcribe", frozenset({"es"}), frozenset({"Latn"}), mac_memory_gb=8), list(seed_cards()))
    correct = next(s for s in recipe["steps"] if s["job"] == "correct")
    assert "gap" in correct and "memory" in correct["gap"]


def test_every_kraken_reader_card_names_an_id_this_mac_can_fetch_and_run():
    """Setup proposes only readers Fichero can download and run: a catalogue reader, or any reader
    in Kraken's repository by its DOI (kraken-zenodo-<n>). PP-OCRv6 used to be proposed by setup and
    then refused by Start, because the download path took catalogue ids only."""
    from fichero_server.llm.kraken_runtime import recognition_spec
    from fichero_server.recipes.cards import kraken_reader_for

    readers = [kraken_reader_for(c.pin) for c in seed_cards() if c.id.startswith("kraken:") and "zenodo" in c.pin]
    assert "kraken-zenodo-21788410" in readers
    assert all(recognition_spec(r) for r in readers)
