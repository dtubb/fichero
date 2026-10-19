"""An optional step joins the plan only when the person ticks it or says yes (owner ruling 2026-10-19, #5812).

Correct, Find where the readers disagree, cloud and training are off until asked. The answer drives the plan, never
the plan the answer: an unanswered or unticked question gives a plan with no Correct step, no disagree step, and so
no download queued for either (a corrector at hand does not put Correct in).
"""

from __future__ import annotations

from fichero_server.recipes.assemble import CORRECT_QUESTION, Answers, assemble
from fichero_server.recipes.start import DISAGREE_JOB, plan_start
from tests.unit.recipes.test_assemble_by_rule import CARDS

BASE = {"purposes": ("transcribe",), "languages": frozenset({"es"}), "scripts": frozenset({"Latn"}),
        "materials": ("handwriting",)}


def _jobs(**more):
    return [s["job"] for s in assemble(Answers(**BASE, **more), CARDS)["steps"]]


def test_an_unanswered_question_gives_no_correct_and_no_disagree_step():
    jobs = _jobs()
    assert "correct" not in jobs and DISAGREE_JOB not in jobs


def test_an_unticked_question_gives_no_correct_step_and_says_what_turning_it_on_costs():
    recipe = assemble(Answers(**BASE, job_answers={CORRECT_QUESTION: False}), CARDS)
    assert "correct" not in [s["job"] for s in recipe["steps"]]
    assert [o for o in recipe["left_off"] if o["job"] == "correct"]


def test_a_yes_puts_correct_in():
    assert "correct" in _jobs(job_answers={CORRECT_QUESTION: True})


def test_ticking_correct_on_its_own_puts_it_in():
    assert "correct" in _jobs(jobs=("correct",))


def test_disagree_joins_only_when_ticked():
    assert DISAGREE_JOB in _jobs(jobs=(DISAGREE_JOB,))
    assert DISAGREE_JOB not in _jobs(job_answers={CORRECT_QUESTION: True})


def test_the_unasked_plan_queues_no_download_for_correct_or_disagree():
    recipe = assemble(Answers(**BASE), CARDS)
    plan = plan_start(recipe, stays_local=True)
    assert not [r for r in plan["runs"] if r["job"] in ("correct", DISAGREE_JOB)]
    assert not [d for d in plan.get("downloads") or [] if set(d.get("steps") or []) & {"correct", DISAGREE_JOB}]
