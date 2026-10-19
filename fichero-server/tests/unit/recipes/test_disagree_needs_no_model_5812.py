"""Find where the readers disagree needs no model of its own (#5812).

Spec: `source.disagree.built-in-with-two-readers` and `source.disagree.one-reader-says-which-to-add`
(docs/contributor_manual/specs/source/readings-and-apparatus.md). WHY: on Set Up > Ready the step said "No model on this
Mac does this yet" and sent the person to a text-model search for a step that only compares readers.
"""

from __future__ import annotations

from fichero_server.recipes.start import DISAGREE_JOB, plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import LINES, SEVEN, mac  # noqa: F401 (fixture)

KRAKEN = {"zenodo": "10.5281/zenodo.13788177"}
KRAKEN_READS = {"id": "read", "job": "read-a-line", "model": KRAKEN}
CORRECT = {"id": "correct", "job": "correct", "model": SEVEN, "runs_on": "this-mac"}
DOUBT = {"id": "doubt", "job": DISAGREE_JOB}


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t/disagree", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_a_plan_with_two_readers_has_no_run_and_lists_the_step_as_built_in_never_as_skipped(mac):
    """#5816, owner ruling: built in is never a warning. The step is in `built_in` with its sentence, not in `skipped`
    (which the app draws as problems), and nothing else about the plan calls it off this Mac or without a model."""
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, DOUBT), stays_local=True)

    assert not [r for r in plan["runs"] if r["job"] == DISAGREE_JOB], "nothing runs and nothing is stored"
    assert not [s for s in plan["skipped"] if s["step"] == "doubt"]
    (built,) = plan["built_in"]
    assert built["step"] == "doubt" and "worked out when you open a page" in built["sentence"]


def test_a_step_that_names_its_own_model_is_still_sampled(mac):
    step = {**DOUBT, "model": SEVEN}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, step), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 5 and all(r["card"] == "workflow" for r in sampled)


def test_one_reader_that_cannot_be_sampled_says_which_reader_to_add_and_offers_no_model(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, DOUBT), stays_local=True)

    (skipped,) = [s for s in plan["skipped"] if s["step"] == "doubt"]
    assert not plan["built_in"], "one reader that cannot be sampled is a problem to fix, not a built-in step"
    assert "add a second reader" in skipped["why"]
    assert skipped["fix"] is None, "no Choose a model for a step that needs none"
    assert not plan.get("needs_a_model")


def test_the_finder_for_a_sampled_reader_offers_vision_readers_never_a_text_search(monkeypatch):
    """`source.disagree.one-reader-says-which-to-add`: the chooser for a step that samples one reader is the readers'
    finder kept to models the plan can sample, and its sources are the readers' (no 'No online search for this step')."""
    from types import SimpleNamespace

    from fichero_server.recipes import discovery

    sampleable = SimpleNamespace(pin={"cloud": "anthropic", "model": "claude-sonnet"})
    kraken = SimpleNamespace(pin={"zenodo": "10.5281/zenodo.13788177"})
    asked = {}

    def readers(a, *, online, search=None, not_searched=None, job="read-a-line"):
        asked["job"] = job
        return [sampleable, kraken], [{"source": "hugging-face", "state": "cached", "count": 0, "detail": "x"}]

    real = discovery.discover
    monkeypatch.setattr(discovery, "discover", lambda *a, **k: real(*a, **k) if k.get("job") == "find-where-readers-disagree" else readers(*a, **k))
    cards, sources = discovery.discover(SimpleNamespace(), online=False, job="find-where-readers-disagree")

    assert asked["job"] == "read-a-line"
    assert cards == [sampleable], "Kraken cannot be sampled as a vision model"
    assert not [s for s in sources if s["detail"] == discovery.NO_STEP_SEARCH]


def _assembled(*jobs):
    from fichero_server.recipes.assemble import Answers, assemble
    from tests.unit.recipes.test_assemble_by_rule import CARDS

    return assemble(Answers(purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                            materials=("handwriting",), jobs=tuple(jobs)), CARDS)


def test_ticked_with_one_reader_the_step_is_built_in_says_it_needs_a_second_reader_and_never_blocks_start(mac):
    """`source.disagree.built-in-needs-second-reader` (#5812): never "has no model", never a Choose a model, Start goes."""
    recipe = _assembled(DISAGREE_JOB)
    (step,) = [s for s in recipe["steps"] if s["job"] == DISAGREE_JOB]
    assert step["built_in"] and not step.get("gap") and not step.get("problem")
    assert step["needs"] == "needs a second reader: tick one in Read"
    assert not [g for g in recipe["gaps"] if DISAGREE_JOB in g]
    assert not step.get("needed_by"), "Remove from Plan always works for the comparison"

    plan = plan_start(recipe, stays_local=True)
    (skipped,) = [s for s in plan["skipped"] if s["step"] == DISAGREE_JOB]
    assert "second reader" in skipped["why"] and skipped["fix"] is None
    assert not plan.get("needs_a_model") and plan["runs"], "the other steps still start"


def test_ticked_with_two_readers_the_step_names_them_and_is_built_in(mac):
    recipe = _assembled(DISAGREE_JOB, "correct")
    (step,) = [s for s in recipe["steps"] if s["job"] == DISAGREE_JOB]
    assert step["built_in"] and "needs" not in step and len(step["compares"]) == 2
    assert not step.get("needed_by"), "Remove from Plan always works for the comparison"
    assert step["reasons"][0].startswith("Compares ") and step["compares"][0] in step["reasons"][0]
    plan = plan_start(recipe, stays_local=True)
    assert [b["step"] for b in plan["built_in"]] == [DISAGREE_JOB] and not plan["skipped"]


def test_one_vision_reader_is_still_sampled_and_one_kraken_reader_needs_a_second(mac):
    """Review 316: `needs a second reader` is said only when the one reader cannot be sampled (Kraken); a vision reader
    is read again several times at a temperature, as `source.disagree.recipe-step` has it."""
    from fichero_server.recipes.assemble import _disagree_step

    built_in = {**DOUBT, "built_in": True, "model": {"builtin": "reader-comparison"}}
    vision = {"id": "read", "job": "read-a-line", "model": SEVEN, "runs_on": "this-mac"}

    sampled = plan_start(_recipe(LINES, vision, built_in), stays_local=True)
    assert len([r for r in sampled["runs"] if r["job"] == DISAGREE_JOB]) == 5 and not sampled["skipped"]

    kraken = plan_start(_recipe(LINES, KRAKEN_READS, built_in), stays_local=True)
    (skipped,) = [s for s in kraken["skipped"] if s["step"] == "doubt"]
    assert "second reader" in skipped["why"] and skipped["fix"] is None

    # The plan's own words follow the same rule.
    assert "needs" not in _disagree_step([{**vision, "card": {"note": "Qwen"}}])
    assert "second reader" in _disagree_step([{**KRAKEN_READS, "card": {"note": "Kraken"}}])["needs"]
