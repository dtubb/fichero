"""Leave Out has its Set Up control (`source.recipe.leave-out-stage`, #6070): the Leave Out stage asks one yes-or-no
question, `leave_out`, saved with the other stage answers (`job_answers`) by the existing setup save, and the plan follows
it. Unanswered it shows what the plan has; answered no the step is out, answered yes it is in. Through the real routes."""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import normalise

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "mac_memory_gb": 16}


def _jobs(client, **answers):
    r = client.post("/api/recipes/assemble", json={**ANSWERS, **answers})
    assert r.status_code == 200, r.text
    return [s["job"] for s in r.json()["steps"]]


def _question(client):
    stage = next(s for s in client.get("/api/recipes/stages").json()["items"] if s["id"] == "leave-out")
    return next(q for q in stage["questions"] if q["key"] == "leave_out")


def test_the_leave_out_stage_asks_one_yes_no_question(client):
    question = _question(client)
    assert question["kind"] == "yes-no" and question["ask"]


def test_no_takes_the_step_out_and_yes_puts_it_in(client, with_material):
    assert "leave-out" in _jobs(client)
    assert "leave-out" not in _jobs(client, job_answers={"leave_out": False})
    assert "leave-out" in _jobs(client, job_answers={"leave_out": True})


def test_yes_adds_nothing_where_there_are_no_lines_to_find(client, with_material):
    assert "leave-out" not in _jobs(client, materials=["text"], job_answers={"leave_out": True})


def test_the_answer_is_saved_and_read_back_by_the_stage_list(client, with_material):
    recipe = client.post("/api/recipes/assemble", json={**ANSWERS, "job_answers": {"leave_out": False}}).json()
    saved = client.put("/api/recipes/project", json={"answers": {**ANSWERS, "job_answers": {"leave_out": False}},
                                                     "recipe": recipe})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/recipes/project").json()["answers"]["job_answers"]["leave_out"] is False
    assert _question(client)["answer"] is False


def test_with_no_plan_yet_it_shows_the_default(client):
    assert _question(client)["answer"] is True


def test_unanswered_it_shows_what_the_saved_plan_has(client, with_material):
    recipe = client.post("/api/recipes/assemble", json=ANSWERS).json()
    assert client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": recipe}).status_code == 200
    assert _question(client)["answer"] is True
    without = [s for s in recipe["steps"] if s["job"] != "leave-out"]
    assert client.put("/api/recipes/project", json={"answers": ANSWERS, "recipe": {**recipe, "steps": without}}).status_code == 200
    assert _question(client)["answer"] is False


@pytest.mark.parametrize("bad", ["yes", 1, [True]])
def test_an_answer_that_is_not_yes_or_no_is_refused_in_words(bad):
    with pytest.raises(ValueError, match="Leave Out is yes or no"):
        normalise({"job_answers": {"leave_out": bad}}, strict=True)


def test_a_step_taken_out_on_ready_shows_no_whatever_answer_was_saved(client, with_material):
    """The saved answer said yes, then the step was taken out of the plan: the toggle shows the plan, not the stale yes."""
    answers = {**ANSWERS, "job_answers": {"leave_out": True}}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    without = [s for s in recipe["steps"] if s["job"] != "leave-out"]
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": {**recipe, "steps": without}}).status_code == 200
    assert _question(client)["answer"] is False
