"""`source.project.record-rule` (spec review 2026-10-20): the rule was set in a recipe's `defaults:` and never read, so
'relaxed' could not be reached. The project's saved recipe says; anything not exactly 'relaxed' is strict."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.models.readings import ProjectRecordRule, project_record_rule
from fichero_server.recipes.project import write_project_setup


class _Db:
    def __init__(self, folder: Path) -> None:
        self.path = folder / "library.duckdb"


def _recipe(rule):
    defaults = {} if rule is None else {"record_rule": rule}
    return {"fichero_recipe": 1, "id": "t", "title": "t", "purposes": [], "steps": [], "defaults": defaults}


def test_a_project_with_no_recipe_is_strict(tmp_path):
    assert project_record_rule(_Db(tmp_path)) is ProjectRecordRule.strict


@pytest.mark.parametrize(("saved", "rule"), [
    ("relaxed", ProjectRecordRule.relaxed), ("Relaxed", ProjectRecordRule.relaxed), ("strict", ProjectRecordRule.strict),
    (None, ProjectRecordRule.strict), ("loose", ProjectRecordRule.strict), ("", ProjectRecordRule.strict)])
def test_the_saved_recipes_default_decides_and_a_word_nobody_knows_is_strict(tmp_path, saved, rule):
    write_project_setup(tmp_path, None, _recipe(saved))
    assert project_record_rule(_Db(tmp_path)) is rule


def test_a_changed_recipe_is_read_again(tmp_path):
    write_project_setup(tmp_path, None, _recipe("relaxed"))
    assert project_record_rule(_Db(tmp_path)) is ProjectRecordRule.relaxed
    write_project_setup(tmp_path, None, _recipe("strict"))
    assert project_record_rule(_Db(tmp_path)) is ProjectRecordRule.strict
