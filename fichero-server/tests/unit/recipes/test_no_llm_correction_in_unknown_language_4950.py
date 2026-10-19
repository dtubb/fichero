"""`source.recipe.no-llm-correction-in-unknown-language` (#4950): a correction or normalising step by a language model
is included only when the model's card lists the project's language; otherwise it is left out and the recipe says
why. The one exception is a frontier cloud model, counted as multilingual and only ever offered (#5718).

WHY: a model asked to correct or normalise a language it does not know rewrites the page into one it does.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.assemble import Answers, Card, _refusal, _sentence, assemble

ARABIC = Answers(purposes=("translate-normalise",), languages=frozenset({"ar"}), scripts=frozenset({"Arab"}),
                 materials=("handwriting",))


def _card(job, languages):
    return Card(id=f"{job}-{'-'.join(sorted(languages or ['none']))}", pin={"hf": "x/y"}, jobs=frozenset({job}),
                scripts=None, languages=None if languages is None else frozenset(languages), material=frozenset())


@pytest.mark.parametrize("job", ["correct", "translate-transliterate-normalise"])
def test_a_model_that_does_not_list_the_language_never_corrects_or_normalises_it(job):
    assert _refusal(job, _card(job, {"en", "es"}), ARABIC, "handwriting")[0] == "no-model-for-language"
    assert _refusal(job, _card(job, None), ARABIC, "handwriting")[0] == "no-model-for-language"  # lists none
    assert _refusal(job, _card(job, {"ar"}), ARABIC, "handwriting") is None
    assert "knows Arabic" in _sentence("no-model-for-language", job, ARABIC, "handwriting")


def test_the_recipe_leaves_the_step_without_that_model_and_says_why():
    recipe = assemble(ARABIC, [_card("translate-transliterate-normalise", {"en"})])
    [step] = [s for s in recipe["steps"] if s["job"] == "translate-transliterate-normalise"]
    assert not step.get("model")
    assert "Arabic" in (step.get("problem") or {}).get("sentence", "") + " ".join(recipe["gaps"]), (step, recipe["gaps"])
