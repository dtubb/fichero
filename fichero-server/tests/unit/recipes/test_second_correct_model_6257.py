"""A second Review the reading model (#6257): answering yes to "Add a second model to review in turn?" adds a second
`correct` step, `correct-2`, after the first with its own model; its text goes to the first's corrected reading, so they
review in turn by default; `second_review_mode` says compare or both instead (owner 2026-10-29, `source.recipe.second-reviewer`),
read as the second step's `review_mode` setting and sent to the review tool by Start. Through the assemble route."""
from __future__ import annotations

import pytest

from fichero_server.recipes.answers import normalise
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_disagree_needs_no_model_5812 import CORRECT, KRAKEN_READS, LINES, _recipe
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

ANSWERS = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
           "mac_memory_gb": 32, "cloud_allowed": False}
ASKED = {"correct_with_a_second_model": True}


def _ids(client, **answers):
    r = client.post("/api/recipes/assemble", json={**ANSWERS, **answers})
    assert r.status_code == 200, r.text
    return [(s["id"], s["job"]) for s in r.json()["steps"]], r.json()


def test_yes_adds_a_second_correct_step_after_the_first(client, with_material, mac):  # noqa: F811
    steps, _ = _ids(client, job_answers={**ASKED, "correct_with_another_model": True})
    ids = [i for i, j in steps if j == "correct"]
    assert ids == ["correct", "correct-2"], steps


def test_without_the_answer_or_without_correct_there_is_one_or_none(client, with_material, mac):  # noqa: F811
    steps, _ = _ids(client, job_answers=ASKED)
    assert [i for i, j in steps if j == "correct"] == ["correct"]
    steps, _ = _ids(client, job_answers={"correct_with_another_model": True})
    assert not [i for i, j in steps if j == "correct"], steps


def test_the_second_review_has_its_own_title(client, with_material, mac):  # noqa: F811
    _, recipe = _ids(client, job_answers={**ASKED, "correct_with_another_model": True})
    titles = {s["id"]: s["title"] for s in recipe["steps"] if s["job"] == "correct"}
    assert titles == {"correct": "Review the reading", "correct-2": "Review the reading again"}


def _second(recipe):
    return next(s for s in recipe["steps"] if s["id"] == "correct-2")


@pytest.mark.parametrize("mode", ["compare", "both"])
def test_the_chosen_mode_is_the_second_steps_setting_and_never_the_firsts(client, with_material, mac, mode):  # noqa: F811
    _, recipe = _ids(client, job_answers={**ASKED, "correct_with_another_model": True, "second_review_mode": mode})
    assert _second(recipe)["settings"] == {"review_mode": mode}
    assert "review_mode" not in (next(s for s in recipe["steps"] if s["id"] == "correct").get("settings") or {})


@pytest.mark.parametrize("answer", [{}, {"second_review_mode": "in-turn"}])
def test_in_turn_is_the_default_and_sets_nothing(client, with_material, mac, answer):  # noqa: F811
    _, recipe = _ids(client, job_answers={**ASKED, "correct_with_another_model": True, **answer})
    assert "review_mode" not in (_second(recipe).get("settings") or {})


def test_a_mode_with_no_second_model_changes_nothing(client, with_material, mac):  # noqa: F811
    steps, _ = _ids(client, job_answers={**ASKED, "second_review_mode": "both"})
    assert [i for i, j in steps if j == "correct"] == ["correct"]


def test_set_up_asks_the_mode_as_a_one_choice_question_read_by_a_step(client):
    read = next(s for s in client.get("/api/recipes/stages").json()["items"] if s["id"] == "read")
    q = next(q for q in read["questions"] if q["key"] == "second_review_mode")
    assert q["kind"] == "one" and q["default"] == "in-turn" and q["read_by_a_step"]
    assert [o["id"] for o in q["options"]] == ["in-turn", "compare", "both"]


@pytest.mark.parametrize("mode", ["in-turn", "compare", "both"])
def test_a_good_mode_is_kept(mode):
    assert normalise({"job_answers": {"second_review_mode": mode}}, strict=True)["job_answers"]["second_review_mode"] == mode


def test_a_mode_nobody_defined_is_refused_naming_the_valid_ones():
    with pytest.raises(ValueError, match="in-turn, compare, both; not 'together'"):
        normalise({"job_answers": {"second_review_mode": "together"}}, strict=True)


def test_start_sends_the_mode_to_the_review_tool(mac):  # noqa: F811
    mac.installed.add("Qwen2.5-VL-7B")
    second = {**CORRECT, "id": "correct-2", "settings": {"review_mode": "compare"}}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, second), stays_local=True)
    runs = {r["steps"][0]: r for r in plan["runs"] if r["job"] == "correct"}
    assert runs["correct-2"]["tool_config"]["transcribe_review"]["review_mode"] == "compare"
    assert "review_mode" not in (runs["correct"].get("tool_config") or {}).get("transcribe_review", {})


@pytest.mark.parametrize("mode", ["compare", "both"])
def test_a_mode_with_the_certainty_bar_is_refused_in_words_not_ignored(mac, mode):  # noqa: F811
    mac.installed.add("Qwen2.5-VL-7B")
    second = {**CORRECT, "id": "correct-2", "settings": {"review_mode": mode}}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, second), stays_local=True,
                      job_answers={"review_certainty_bar": "0.5"})
    (skipped,) = [s for s in plan["skipped"] if s["step"] == "correct-2"]
    assert mode in skipped["why"] and "unsure of" in skipped["why"]
    assert [r["steps"][0] for r in plan["runs"] if r["job"] == "correct"] == ["correct"]


def test_in_turn_with_the_certainty_bar_is_as_before(mac):  # noqa: F811
    mac.installed.add("Qwen2.5-VL-7B")
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT, {**CORRECT, "id": "correct-2"}), stays_local=True,
                      job_answers={"review_certainty_bar": "0.5"})
    assert [r["steps"][0] for r in plan["runs"] if r["job"] == "correct"] == ["correct", "correct-2"]
