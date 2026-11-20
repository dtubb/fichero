"""`designer.filter.fit-first` (#6733 item 5): a reader whose card states no script is not ranked for every script;
one that states the project's script ranks above it."""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, _choose

HEBREW = Answers(purposes=("transcribe",), languages=frozenset({"he"}), scripts=frozenset({"Hebr"}),
                 materials=("handwriting",), material="handwriting", cloud_allowed=True)
UNSTATED = Card(id="a-unstated", pin={"hf": "x/a"}, jobs=frozenset({"read-a-line"}), scripts=None, languages=None,
                material=frozenset({"handwriting"}), cer_published=0.01)
MATCHED = Card(id="z-hebrew", pin={"hf": "x/z"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Hebr"}),
               languages=frozenset({"he"}), material=frozenset({"handwriting"}))


def test_a_reader_that_states_the_script_ranks_above_one_that_states_none():
    choice = _choose("read-a-line", [UNSTATED, MATCHED], HEBREW)
    assert choice.card.id == "z-hebrew"
    assert [c.id for c in choice.chain] == ["a-unstated"]


def test_a_card_that_states_no_script_still_serves_a_job_that_reads_no_text():
    finder = Card(id="finder", pin={"builtin": "f"}, jobs=frozenset({"find-lines"}), scripts=None, languages=None,
                  material=frozenset({"handwriting"}))
    assert _choose("find-lines", [finder], HEBREW).card.id == "finder"
