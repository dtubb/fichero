"""`source.recipe.no-other-style-substitute` (#4951): a reader made for another style of the project's script (naskh
for nastaliq) is never proposed in its place; the step is "needs a model" and the gap is named.

WHY: a naskh reader reads nastaliq badly enough to look like a result; proposed as the reader, it would read the
whole archive wrong with a confident card.
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, _refusal, assemble

NASTALIQ = Answers(purposes=("transcribe",), languages=frozenset({"fa"}), scripts=frozenset({"Aran"}),
                   materials=("handwriting",))
NASKH = Card(id="naskh-reader", pin={"hf": "x/naskh"}, jobs=frozenset({"read-a-line"}), scripts=frozenset({"Arab"}),
             languages=frozenset({"fa"}), material=frozenset({"handwriting"}), note="A naskh reader",
             cer_published=0.05)


def test_a_reader_for_another_style_of_the_script_is_refused():
    assert _refusal("read-a-line", NASKH, NASTALIQ, "handwriting")[0] == "no-model-for-script"


def test_the_step_needs_a_model_and_names_the_other_style_as_nearest_never_as_its_reader():
    recipe = assemble(NASTALIQ, [NASKH])
    [step] = [s for s in recipe["steps"] if s["job"] == "read-a-line"]
    assert not step.get("model") and NASKH.id not in str(step.get("card"))  # never its reader
    problem = step["problem"]
    assert problem["kind"] == "no-model-for-script"
    assert [n["card"] for n in problem["nearest"]] == [NASKH.id] and "related script" in problem["nearest"][0]["why"]
