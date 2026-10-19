"""`source.job.review-is-built-from-the-project-and-a-profile` (#5723): the recipe's review step turns its lenses on
or off (setup's `job_answers.review_lenses`, the step's `lenses`). A lens turned off is not run: its pass leaves the
review preset and the passes either side of it are chained; a pass through several lenses keeps only those on.

WHY: the three lenses always ran, whatever the project asked for, at three reviews' cost per page.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.recipes import start
from fichero_server.recipes.review_profiles import keep_lenses
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

PRESETS = Path(__file__).parents[3] / "src/fichero_server/resources/default_workflows"


def _preset(name):
    w = json.loads((PRESETS / f"{name}.json").read_text())
    return w["nodes"], w["edges"]


def _chain(edges):
    return {(e["source"], e["target"]) for e in edges if e.get("target_port") == "context"}


def test_all_lenses_on_leaves_the_preset_as_it_is():
    nodes, edges = _preset("transcribe_paleography_review")
    assert keep_lenses(nodes, edges, ["abbreviations", "orthography", "names-and-dates"]) == (nodes, edges)


def test_a_lens_turned_off_leaves_the_preset_and_the_passes_either_side_are_chained():
    nodes, edges = _preset("transcribe_paleography_review")
    kept, wired = keep_lenses(nodes, edges, ["abbreviations", "names-and-dates"])
    assert [n["id"] for n in kept if n["tool"] == "transcribe_review"] == ["r1", "r3"]
    assert _chain(wired) == {("r1", "r3")}
    assert not [e for e in wired if "r2" in (e["source"], e["target"])]
    assert "reference-search" not in {n["id"] for n in kept}  # it fed only the pass that left: it goes too


def test_a_pass_through_several_lenses_keeps_only_those_on():
    nodes, edges = _preset("transcribe_auto_detect")
    kept, _ = keep_lenses(nodes, edges, ["orthography"])
    assert {n["config"]["lens"] for n in kept if n["tool"] == "transcribe_review"} == {"orthography"}


def test_the_steps_lenses_reach_its_run_in_the_profiles_order(monkeypatch):
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs: [])
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False,
                      job_answers={"review_lenses": ["names-and-dates", "abbreviations"]})
    [run] = [r for r in plan["runs"] if "correct" in r["steps"]]
    assert run["lenses"] == ["abbreviations", "names-and-dates"]


def test_every_lens_off_skips_the_step_and_says_so(monkeypatch):
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs: [])
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False, job_answers={"review_lenses": []})
    assert not [r for r in plan["runs"] if "correct" in r["steps"]]
    assert any(s["step"] == "correct" and "lens" in s["why"] for s in plan["skipped"]), plan["skipped"]


def test_a_lens_fichero_does_not_have_is_refused_in_words():
    from fichero_server.recipes.answers import normalise

    with pytest.raises(ValueError, match="lens"):
        normalise({"purposes": ["transcribe"], "job_answers": {"review_lenses": ["palaeography"]}}, strict=True)


def test_the_runner_runs_the_preset_without_the_lenses_turned_off(db, monkeypatch):
    from fichero_server.recipes import runner

    seen = {}

    def validate(workflow, request, db):
        seen["nodes"] = [n["id"] for n in workflow.nodes]
        raise ValueError("stop here")

    from fichero_server.api.routes.workflow import chains
    from fichero_server.models import Workflow
    from fichero_server.workflows import default_workflows

    shipped = Workflow(**json.loads((PRESETS / "transcribe_paleography_review.json").read_text()))
    monkeypatch.setattr(chains, "_load_step_workflow", lambda db, workflow_id: None)
    monkeypatch.setattr(default_workflows, "resolve_shipped_workflow", lambda db, workflow_id, name: shipped)
    monkeypatch.setattr(chains, "_validate_step_workflow", validate)
    name, workflow_id = start._shipped(start.WORKFLOW_FOR_JOB["correct"])
    card = {"workflow": name, "workflow_id": workflow_id, "provider_override": "openai", "model_override": "gpt-5",
            "lenses": ["orthography"]}
    assert runner._run_workflow(db, card, ["p1"], "recipe-job")[1:] == ("failed", "stop here")
    assert "r1" not in seen["nodes"] and "r3" not in seen["nodes"] and "r2" in seen["nodes"]


def test_two_passes_off_in_a_row_leave_no_edge_to_a_pass_that_left():
    nodes, edges = _preset("transcribe_paleography_review")
    kept, wired = keep_lenses(nodes, edges, ["names-and-dates"])
    ids = {n["id"] for n in kept}
    assert {n["id"] for n in kept if n["tool"] == "transcribe_review"} == {"r3"}
    assert all(e["source"] in ids and e["target"] in ids for e in wired)


def test_the_middle_lens_alone_keeps_its_pass_and_drops_the_search_that_lost_its_query():
    nodes, edges = _preset("transcribe_paleography_review")
    kept, wired = keep_lenses(nodes, edges, ["orthography"])
    assert [n["id"] for n in kept] == ["files-source", "r2"]
    assert {(e["source"], e["target"]) for e in wired} == {("files-source", "r2")}
