"""The Read page's "Have a second model check the reading?" and the plan's Correct step agree (#5812).

WHY: the box was unticked while the Qwen2.5-VL Correct step sat in the plan above it; two sources of truth.
`read_project_setup` is the one read of a project's answers and recipe, so the answer is made to say what the plan has.
"""

from __future__ import annotations

from fichero_server.recipes.assemble import CORRECT_QUESTION
from fichero_server.recipes.project import read_project_setup, write_project_setup

CORRECT_STEP = {"id": "correct", "job": "correct"}
READ_STEP = {"id": "read", "job": "read-a-line"}
BASE = {"purposes": ["transcribe"], "languages": ["es"]}


def _setup(tmp_path, job_answers, steps):
    answers = {**BASE, **({"job_answers": job_answers} if job_answers is not None else {})}
    write_project_setup(tmp_path, answers, {"fichero_recipe": 1, "steps": steps})
    return read_project_setup(tmp_path)["answers"]


def test_a_plan_with_the_correct_step_reads_as_ticked_when_never_answered(tmp_path):
    answers = _setup(tmp_path, None, [READ_STEP, CORRECT_STEP])
    assert answers["job_answers"][CORRECT_QUESTION] is True


def test_a_plan_without_the_step_does_not_read_as_ticked(tmp_path):
    answers = _setup(tmp_path, None, [READ_STEP])
    assert CORRECT_QUESTION not in (answers.get("job_answers") or {})


def test_an_answer_the_person_gave_is_kept(tmp_path):
    answers = _setup(tmp_path, {CORRECT_QUESTION: False}, [READ_STEP, CORRECT_STEP])
    assert answers["job_answers"][CORRECT_QUESTION] is False


def test_other_answers_under_a_purpose_are_kept_beside_it(tmp_path):
    answers = _setup(tmp_path, {"some_other_question": "x"}, [READ_STEP, CORRECT_STEP])
    assert answers["job_answers"] == {"some_other_question": "x", CORRECT_QUESTION: True}
