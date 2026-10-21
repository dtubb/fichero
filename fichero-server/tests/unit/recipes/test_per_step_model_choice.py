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


def test_a_cloud_reader_in_the_pool_makes_the_cloud_question_name_the_read_step():
    recipe = assemble(_handwriting(), [*CARDS, CLOUD_READER])
    assert "read-a-line" in recipe["cloud_options"]  # assemble counts any cloud card it is given; the pool is what is short


def test_handwriting_with_the_permission_and_a_key_picks_the_cloud_reader_and_says_it_is_unmeasured():
    """`source.recipe.reader-pick-from-the-material`: the cloud reader is the person's provider row (`readers`), the rules' pick is the chain's next."""
    answers = _handwriting(cloud_allowed=True, cloud_keys=("anthropic",))
    step = next(s for s in assemble(answers, CARDS, readers=[CLOUD_READER])["steps"] if s["job"] == "read-a-line")
    assert str(step["runs_on"]).startswith("cloud:") and any("unmeasured" in r for r in step["reasons"])
    assert step["chain"] and not str(step["chain"][0]["runs_on"]).startswith("cloud:")
    no_key = assemble(_handwriting(cloud_allowed=True), CARDS, readers=[CLOUD_READER])
    assert next(s for s in no_key["steps"] if s["job"] == "read-a-line")["runs_on"] == "this-mac"


def test_without_the_permission_or_for_print_the_local_pick_stands():
    no_permission = assemble(_handwriting(cloud_keys=("anthropic",)), [*CARDS, CLOUD_READER])
    assert next(s for s in no_permission["steps"] if s["job"] == "read-a-line")["runs_on"] == "this-mac"
    printed = Answers("search", frozenset({"es"}), frozenset({"Latn"}), "print", pages=3000, cloud_allowed=True,
                      cloud_keys=("anthropic",))
    assert next(s for s in assemble(printed, [*CARDS, CLOUD_READER])["steps"] if s["job"] == "read-a-line")["runs_on"] == "this-mac"


def test_the_unsure_lines_pass_is_the_correct_step_with_only_below_confidence():
    from fichero_server.recipes.jobs import get_job

    assert "only_below_confidence" in get_job("correct").settings


def _rows():
    from fichero_server.recipes import bakeoff

    return bakeoff.candidates(_handwriting(cloud_allowed=True, cloud_keys=("anthropic",)), [*CARDS, CLOUD_READER], volume=100)


@pytest.mark.xfail(strict=True, reason="source.recipe.kraken-reads-cloud-corrects-unsure: not offered as a choice in the Set Up plan (#4951, #5922)")
def test_the_plan_lists_the_unsure_lines_option_beside_the_cloud_reader():
    rows = _rows()
    assert any(r.get("variant") == "kraken-then-cloud-unsure-lines" for r in rows), "no row carries the unsure-lines variant"
    assert any(r["card"] == "claude-reader" for r in rows)


# The plan's per-step candidates are pinned in test_step_choices_on_the_plan.py (the settled `StartPlan.step_choices` shape).


# The saved cloud choice with no key or permission is pinned in test_step_choices_on_the_plan.py (the plan skips it in place).
