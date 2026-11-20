"""`designer.filter.fit-first` (#6733 item 1): period and material rank before "made for the script", so a
15th-century handwriting reader never outranks a print-era reader for 18th-century print; a Kraken repository card
carries the period its own words name."""
from __future__ import annotations

from dataclasses import replace

from fichero_server.recipes.assemble import Answers, Card, _choose
from fichero_server.recipes.discovery import _row_period, repository_cards

GERMAN_PRINT = Answers(purposes=("transcribe",), languages=frozenset({"de"}), scripts=frozenset({"Latn"}),
                       materials=("print",), material="print", period="18th century", cloud_allowed=True)
GENERIC = Card(id="generic", pin={"hf": "x/generic"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Latn", "Grek"}),
               languages=None, material=frozenset({"print"}), period=(1700, 1900), cer_published=0.20)
BASTARDA = Card(id="bastarda", pin={"hf": "x/bastarda"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Latn"}),
                languages=frozenset({"de"}), material=frozenset({"handwriting"}), period=(1400, 1500),
                cer_published=0.024)


def test_a_made_for_script_handwriting_reader_does_not_outrank_a_print_reader_of_the_period():
    assert _choose("read-a-line", [BASTARDA, GENERIC], GERMAN_PRINT).card.id == "generic"


def test_material_ranks_before_made_for_script_when_neither_states_a_period():
    a = replace(GERMAN_PRINT, period="")
    hand = replace(BASTARDA, period=None)
    assert _choose("read-a-line", [hand, replace(GENERIC, period=None)], a).card.id == "generic"


def test_the_period_a_record_names_becomes_the_cards_years():
    assert _row_period({"summary": "Handwriting, 15th century", "description": "", "keywords": []}) == (1401, 1500)
    assert _row_period({"summary": "Prints of the 16th-17th centuries", "description": "", "keywords": []}) == (1501, 1700)
    assert _row_period({"summary": "Letters 1650-1700", "description": "", "keywords": []}) == (1650, 1700)
    assert _row_period({"summary": "no period", "description": "", "keywords": []}) is None


def test_a_repository_card_carries_the_period_its_record_names():
    row = {"doi": "10.5281/zenodo.1", "concept_doi": "", "summary": "German bastarda handwriting, 15th century",
           "description": "", "licence": "cc-by-4.0", "scripts": ["Latn"], "languages": ["de"], "keywords": [],
           "cer_percent": 2.4, "size_bytes": 1000, "published": "2024-01-01"}
    [card] = repository_cards([row], [], frozenset({"de"}))
    assert card.period == (1401, 1500)
