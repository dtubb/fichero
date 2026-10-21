"""Per-step model choice in Set Up (owner ruling 2026-10-21; specs `source.onboard.cloud-question-counts-readers`,
`source.recipe.reader-pick-from-the-material`, `source.recipe.cloud-reads-lines-per-page`,
`source.recipe.kraken-reads-cloud-corrects-unsure`, `source.onboard.step-candidates-on-the-plan`,
`source.onboard.step-choice-overrides-the-pick`). The built part passes; each [BROKEN]/[GAP] line has a test marked
xfail(strict=True) that turns into a failure the day the behaviour exists, so the spec tag is moved with it."""
from __future__ import annotations

import pytest

from fichero_server.recipes import discovery
from fichero_server.recipes.assemble import Answers, Card, assemble
from tests.unit.recipes.test_assemble_by_rule import ANY, CARDS

CLOUD_READER = Card("claude-reader", {"cloud": "anthropic", "model": "claude"}, discovery.READER_JOBS, ANY, ANY,
                    frozenset({"handwriting", "print"}), runs_on="cloud:anthropic", cost_per_page=0.01, offered_only=True)


def _handwriting(**kw):
    return Answers("search", frozenset({"es"}), frozenset({"Latn"}), "handwriting", pages=3000, **kw)


@pytest.mark.xfail(strict=True, reason="source.onboard.cloud-question-counts-readers: known_cards holds the text cloud cards only (#4951)")
def test_the_cloud_question_counts_the_cloud_readers(monkeypatch):
    monkeypatch.setattr(discovery, "remote_reader_cards", lambda: [CLOUD_READER])
    cards = discovery.known_cards(_handwriting())
    assert any(c.runs_on.startswith("cloud:") and "read-a-line" in c.jobs for c in cards)


def test_a_cloud_reader_in_the_pool_makes_the_cloud_question_name_the_read_step():
    recipe = assemble(_handwriting(), [*CARDS, CLOUD_READER])
    assert "read-a-line" in recipe["cloud_options"]  # assemble counts any cloud card it is given; the pool is what is short


@pytest.mark.xfail(strict=True, reason="source.recipe.reader-pick-from-the-material: unmeasured, the specialist tier wins (#4951)")
def test_handwriting_with_the_permission_and_a_key_picks_the_cloud_reader():
    answers = _handwriting(cloud_allowed=True, cloud_keys=("anthropic",))
    step = next(s for s in assemble(answers, [*CARDS, CLOUD_READER])["steps"] if s["job"] == "read-a-line")
    assert str(step["runs_on"]).startswith("cloud:")


def test_without_the_permission_or_for_print_the_local_pick_stands():
    no_permission = assemble(_handwriting(cloud_keys=("anthropic",)), [*CARDS, CLOUD_READER])
    assert next(s for s in no_permission["steps"] if s["job"] == "read-a-line")["runs_on"] == "this-mac"
    printed = Answers("search", frozenset({"es"}), frozenset({"Latn"}), "print", pages=3000, cloud_allowed=True,
                      cloud_keys=("anthropic",))
    assert next(s for s in assemble(printed, [*CARDS, CLOUD_READER])["steps"] if s["job"] == "read-a-line")["runs_on"] == "this-mac"


@pytest.mark.xfail(strict=True, reason="source.recipe.cloud-reads-lines-per-page: today's line reader sends LINES_PER_CALL=8 lines a call (#4951, #5955)")
def test_a_cloud_line_reader_makes_one_call_per_page_with_the_crops_in_order():
    from fichero_server.llm.page_line_reader import calls_for

    calls = calls_for({"p1": ["a", "b", "c"], "p2": ["d"]})
    assert [c["page"] for c in calls] == ["p1", "p2"] and calls[0]["crops"] == ["a", "b", "c"]


def test_the_unsure_lines_pass_is_the_correct_step_with_only_below_confidence():
    from fichero_server.recipes.jobs import get_job

    assert "only_below_confidence" in get_job("correct").settings


@pytest.mark.xfail(strict=True, reason="source.recipe.kraken-reads-cloud-corrects-unsure: not offered as a choice in the Set Up plan (#4951, #5922)")
def test_the_plan_lists_the_unsure_lines_option_beside_the_cloud_reader():
    from fichero_server.recipes.candidates import step_candidates

    names = [c["kind"] for c in step_candidates(_handwriting(cloud_allowed=True, cloud_keys=("anthropic",)), "read-a-line")]
    assert "kraken-then-cloud-corrects-unsure" in names and "cloud-reads-kraken-lines" in names


@pytest.mark.xfail(strict=True, reason="source.onboard.step-candidates-on-the-plan: the plan lists no candidates per step (#4951, #5922)")
def test_each_step_lists_its_candidates_with_place_need_cost_and_one_pick():
    from fichero_server.recipes.candidates import step_candidates

    rows = step_candidates(_handwriting(cloud_allowed=True, cloud_keys=("anthropic",)), "read-a-line")
    assert all({"name", "where", "needs", "cost"} <= set(r) for r in rows) and sum(1 for r in rows if r["picked"]) == 1


@pytest.mark.xfail(strict=True, reason="source.onboard.step-choice-overrides-the-pick: a saved cloud choice with no key is not yet said in place (#4951)")
def test_a_saved_cloud_choice_with_no_key_stays_chosen_and_says_what_it_needs():
    from fichero_server.recipes.candidates import step_state

    state = step_state(_handwriting(cloud_allowed=True, cloud_keys=()), "read-a-line", chosen="claude-reader")
    assert state["chosen"] == "claude-reader" and "key" in state["blocked_because"]
