"""`source.job.review-instructions-are-editable` (#6128): a review pass's instructions are the person's edit when they
made one, else the profile-built default; the edit travels in `job_answers.review_instructions` to the run.

WHY: the passes' prompts could not be changed without leaving the recipe for the workflow editor.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fichero_server.recipes import start
from fichero_server.recipes.answers import normalise
from fichero_server.recipes.review_profiles import review_prompt, with_instructions
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

PRESETS = Path(__file__).parents[3] / "src/fichero_server/resources/default_workflows"


def _nodes(name="transcribe_paleography_review"):
    return json.loads((PRESETS / f"{name}.json").read_text())["nodes"]


def test_an_edited_pass_is_sent_the_persons_text_and_the_others_keep_the_default():
    out = {n["id"]: n for n in with_instructions(_nodes(), {"orthography": "Only fix u/v."}, None)}
    assert out["r2"]["config"]["prompt"] == "Only fix u/v."
    assert "prompt" not in out["r1"]["config"] and "prompt" not in out["r3"]["config"]


def test_the_edit_reaches_the_runs_entry_and_a_blank_edit_is_no_edit(monkeypatch):
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs, names=None: [])
    plan = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False,
                      job_answers={"review_instructions": {"orthography": "Only fix u/v.", "abbreviations": "  "}})
    [run] = [r for r in plan["runs"] if "correct" in r["steps"]]
    assert run["review_instructions"] == {"orthography": "Only fix u/v."}


def test_an_instruction_for_a_lens_fichero_does_not_have_is_refused_in_words():
    with pytest.raises(ValueError, match="A review lens is"):
        normalise({"job_answers": {"review_instructions": {"spelling": "x"}}}, strict=True)


def test_a_pass_through_three_lenses_with_one_edited_keeps_the_other_two_defaults():
    [node] = [n for n in _nodes("transcribe_auto_detect") if n.get("tool") == "transcribe_review"][:1]
    lenses = [x.strip() for x in node["config"]["lens"].split(",")]
    assert len(lenses) == 3
    [out] = with_instructions([node], {"orthography": "Only fix u/v."}, None)
    prompt = out["config"]["prompt"]
    assert "Only fix u/v." in prompt
    for other in (x for x in lenses if x != "orthography"):
        assert review_prompt(other, None)[0] in prompt


def test_the_route_says_default_then_edit_then_blank_is_unedited(tmp_path, monkeypatch):
    from fichero_server.api.routes.system import recipes as route

    answers = {}
    monkeypatch.setattr(route, "read_project_setup", lambda lib: {"answers": answers})
    monkeypatch.setattr(route, "_library", lambda db: tmp_path)
    def one():
        return {p.lens: p for p in asyncio.run(route.get_review_instructions(None)).passes}["orthography"]

    assert (one().edited, one().text) == (False, one().default)
    answers["job_answers"] = {"review_instructions": {"orthography": "Only fix u/v."}}
    assert (one().edited, one().text) == (True, "Only fix u/v.") and one().default != "Only fix u/v."
    answers["job_answers"] = {"review_instructions": {"orthography": "  "}}
    assert (one().edited, one().text) == (False, one().default)
