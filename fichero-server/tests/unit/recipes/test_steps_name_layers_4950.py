"""`source.recipe.steps-name-layers` (#4950): every assembled step names its layer, and the recipe's `automatic`
section lists the steps the purpose (or an added layer) turns on, each with whether it may use the cloud."""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, assemble
from fichero_server.recipes.jobs import get_job

from .test_assemble_by_rule import CARDS


def _answers(**kw) -> Answers:
    return Answers(languages=frozenset({"es"}), scripts=frozenset({"Latn"}), material="handwriting",
                   purposes=("search",), **kw)


def test_every_step_names_its_layer():
    recipe = assemble(_answers(), CARDS)
    assert recipe["steps"]
    for step in recipe["steps"]:
        known = get_job(step["job"])
        assert step["layer"] == (known.layer if known else step["layer"]) and step["layer"]


def test_automatic_lists_the_purpose_steps_with_their_cloud_use():
    recipe = assemble(_answers(), CARDS)
    by_id = {s["id"]: s for s in recipe["steps"]}
    assert recipe["automatic"]
    for row in recipe["automatic"]:
        assert set(row) == {"id", "layer", "uses_cloud"}
        assert row["layer"] == by_id[row["id"]]["layer"] and row["uses_cloud"] == by_id[row["id"]]["uses_cloud"]
    # in step order, and only steps that are in the plan
    ids = [r["id"] for r in recipe["automatic"]]
    assert ids == [s["id"] for s in recipe["steps"] if s["id"] in ids]


def test_a_step_ticked_by_hand_is_not_automatic():
    """Ticked on top of a purpose that does not bring it: in the plan, but not automatic."""
    recipe = assemble(Answers(languages=frozenset({"es"}), scripts=frozenset({"Latn"}), material="handwriting",
                              purposes=("search",), jobs=("find-names-tag-words",)), CARDS)
    assert "find-names-tag-words" in {s["id"] for s in recipe["steps"]}
    assert "find-names-tag-words" not in {r["id"] for r in recipe["automatic"]}
