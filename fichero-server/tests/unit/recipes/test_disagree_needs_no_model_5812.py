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


def test_a_plan_with_two_readers_gets_a_built_in_step_with_no_model(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, DOUBT), stays_local=True)

    (run,) = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert run["card"] == "align" and "model_override" not in run and "workflow" not in run
    assert not [s for s in plan["skipped"] if s["step"] == "doubt"]


def test_the_built_in_step_never_sends_pages_off_the_mac(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, DOUBT), stays_local=True)

    assert not [s for s in plan["skipped"] if "off this Mac" in s["why"]]
    assert [r for r in plan["runs"] if r["job"] == DISAGREE_JOB][0]["runs_on"] == "this-mac"


def test_a_step_that_names_its_own_model_is_still_sampled(mac):
    step = {**DOUBT, "model": SEVEN}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, step), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 5 and all(r["card"] == "workflow" for r in sampled)


def test_one_reader_that_cannot_be_sampled_says_which_reader_to_add_and_offers_no_model(mac):
    plan = plan_start(_recipe(LINES, KRAKEN_READS, DOUBT), stays_local=True)

    (skipped,) = [s for s in plan["skipped"] if s["step"] == "doubt"]
    assert "add a second reader" in skipped["why"]
    assert skipped["fix"] is None, "no Choose a model for a step that needs none"
    assert not plan.get("needs_a_model")


def test_the_built_in_run_aligns_each_page_and_a_missing_page_is_said(db, monkeypatch):
    from fichero_server.api.routes.document import compare_readings
    from fichero_server.recipes import runner

    seen = []

    def fake(_db, page_id):
        seen.append(page_id)
        if page_id == "gone":
            raise LookupError("no such page")

    monkeypatch.setattr(compare_readings, "page_disagreement", fake)

    assert runner._run_align(db, ["a", "b"]) == (None, "done", None)
    assert seen == ["a", "b"]
    child, state, why = runner._run_align(db, ["a", "gone"])
    assert (child, state) == (None, "failed") and "1 of 2" in why
