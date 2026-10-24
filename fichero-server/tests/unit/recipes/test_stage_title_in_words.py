"""A recipe run's stage is named in words, from the job registry, never by its job ids.

Spec: `source.activity.run.stage-named-in-words`. WHY: the run status line read "find-lines, read-a-line · stage 1 of 5".
"""
from __future__ import annotations

from fichero_server.recipes.run_view import RecipeRunStep


def test_a_stage_is_titled_with_its_jobs_names_not_their_ids():
    stage = RecipeRunStep(steps=["find-lines", "read-a-line"], card="c", state="running")
    assert stage.title == "Find lines and Read each line"
    assert "find-lines" not in stage.title


def test_a_title_the_status_carries_is_kept():
    stage = RecipeRunStep(steps=["find-lines"], card="c", state="done", title="Lines")
    assert stage.title == "Lines"
