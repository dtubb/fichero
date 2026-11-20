"""`source.recipe.no-cross-script-reader` (#6733 item 2): a variant script matches the card of its parent
(Hant~Hani, Syre/Syrj/Syrn~Syrc; nastaliq stays apart from naskh, #4951), and a German Latn project accepts a Fraktur (Latf) card."""
from __future__ import annotations

import pytest

from fichero_server.recipes.assemble import Answers, Card, _refusal


def _answers(script: str, language: str = "x") -> Answers:
    return Answers(purposes=("transcribe",), languages=frozenset({language}), scripts=frozenset({script}),
                   materials=("print",), material="print", cloud_allowed=True)


def _card(*scripts: str) -> Card:
    return Card(id="c", pin={"hf": "x/c"}, jobs=frozenset({"read-a-line"}), scripts=frozenset(scripts),
                languages=None, material=frozenset({"print"}))


@pytest.mark.parametrize("project,card", [("Hant", "Hani"), ("Hans", "Hani"), ("Syre", "Syrc"),
                                          ("Syrj", "Syrc"), ("Syrn", "Syrc"), ("Latn", "Latf")])
def test_a_variant_project_is_read_by_its_parents_card(project, card):
    assert _refusal("read-a-line", _card(card), _answers(project), "print") is None


def test_the_parent_project_still_does_not_take_another_script():
    assert _refusal("read-a-line", _card("Arab"), _answers("Hant"), "print")[0] == "no-model-for-script"
    assert _refusal("read-a-line", _card("Jpan"), _answers("Hant"), "print")[0] == "no-model-for-script"
    assert _refusal("read-a-line", _card("Hani", "Hira", "Kana"), _answers("Hant"), "print")[0] == "no-model-for-script"
