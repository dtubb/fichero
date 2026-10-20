"""`source.recipe.kraken-then-cloud-unsure-lines`, the bar in Set Up (#5894): the Read stage asks which lines the second
model gets; the answer reaches the `correct` step as `only_below_confidence`; a bad number is refused in words."""
from __future__ import annotations

import pytest

from fichero_server.recipes import stages
from fichero_server.recipes.answers import normalise
from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_disagree_needs_no_model_5812 import CORRECT, KRAKEN_READS, LINES
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401 (fixture)


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t/bar", "version": "0.1.0", "title": "t", "steps": list(steps)}


def _bar_of(plan):
    runs = [r for r in plan["runs"] if r["job"] == "correct"]
    assert len(runs) == 1, (plan["runs"], plan["skipped"])
    run = runs[0]
    return (run.get("tool_config") or {}).get("transcribe_review", {}).get("only_below_confidence")


def test_the_read_stage_asks_it_as_an_ordinary_one_choice_question_with_the_whole_page_as_the_default():
    read = next(s for s in stages.STAGES if s.id == "read")
    q = next(q for q in read.questions if q.key == "review_certainty_bar")
    assert q.kind == "one" and q.default == "whole-page" and q.read_by_a_step
    assert [o[0] for o in q.options] == ["whole-page", "0.5", "0.6", "0.7", "0.8", "0.9"]


def test_a_bar_answer_reaches_the_correct_step_as_only_below_confidence(mac):
    mac.installed.add("Qwen2.5-VL-7B")
    plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT), stays_local=True,
                      job_answers={"review_certainty_bar": "0.7"})
    assert _bar_of(plan) == 0.7


def test_the_whole_page_or_no_answer_sets_no_bar(mac):
    mac.installed.add("Qwen2.5-VL-7B")
    for answers in ({"review_certainty_bar": "whole-page"}, {}, None):
        plan = plan_start(_recipe(LINES, KRAKEN_READS, CORRECT), stays_local=True, job_answers=answers)
        assert _bar_of(plan) is None, answers


def test_a_bar_the_recipe_already_sets_wins_over_the_answer(mac):
    mac.installed.add("Qwen2.5-VL-7B")
    step = {**CORRECT, "settings": {"only_below_confidence": 0.5}}
    plan = plan_start(_recipe(LINES, KRAKEN_READS, step), stays_local=True, job_answers={"review_certainty_bar": "0.9"})
    assert _bar_of(plan) == 0.5


@pytest.mark.parametrize("bad", ["0", "1.5", "-0.2", "sure", True, [0.6]])
def test_a_bar_that_is_not_a_number_above_zero_up_to_one_is_refused_in_words(bad):
    with pytest.raises(ValueError, match="certainty under which a line goes to the second model"):
        normalise({"job_answers": {"review_certainty_bar": bad}}, strict=True)


@pytest.mark.parametrize("good", ["whole-page", "0.6", 0.6, 1, "1"])
def test_a_good_bar_is_kept(good):
    assert normalise({"job_answers": {"review_certainty_bar": good}}, strict=True)["job_answers"][
        "review_certainty_bar"] == good
