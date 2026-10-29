"""`source.recipe.steps-say-what-they-do` (#6250, APPROVED 2026-10-28): the four reading steps carry one plain label
each, the same in Set Up, the plan's step menus and a run's progress, from the job's topic title. Before, the stage
page said "Read lines", "Read pages", "Correct", the topics "Read a page" and "Correct", and the run "Correcting the
readings", so a person could not tell which step was which."""
from __future__ import annotations

from fichero_server.recipes import runner, step_choices

LABELS = {"find-lines": "Find lines", "read-a-line": "Read each line", "read-a-page": "Read the whole page",
          "correct": "Review the reading"}
DOING = {"find-lines": "Finding the lines", "read-a-line": "Reading each line", "read-a-page": "Reading the whole page",
         "correct": "Reviewing the reading"}


def test_the_jobs_names_are_the_labels(client):
    names = {j["id"]: j["name"] for j in client.get("/api/recipes/jobs").json()["items"]}
    assert {j: names[j] for j in LABELS} == LABELS


def test_the_plans_step_menus_use_the_same_labels():
    assert {j: step_choices._STAGE_WORDS[j] for j in LABELS} == LABELS


def test_a_runs_progress_says_what_each_step_is_doing():
    assert {j: runner._DOING[j] for j in DOING} == DOING
