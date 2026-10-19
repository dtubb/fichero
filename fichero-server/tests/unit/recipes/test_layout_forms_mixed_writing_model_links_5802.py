"""#5802: Set Up's layout page. `source.onboard.stages.layout-forms`, `.mixed-writing-per-region`,
`.step-names-its-model` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: the owner testing the staged build (2026-10-19): Find Regions had no Forms choice; a page with manuscript and
typed text had no way to say so; "Which model does it" showed a bare radio button with no model.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from fichero_server.recipes.assemble import Answers, assemble
from fichero_server.recipes.stages import get_stage

# tests/unit/recipes is not a package: load the shared cards by path.
_spec = importlib.util.spec_from_file_location("_assemble_by_rule", Path(__file__).with_name("test_assemble_by_rule.py"))
assert _spec and _spec.loader
_by_rule = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_by_rule)
CARDS = _by_rule.CARDS


def _answers(**kw) -> Answers:
    return Answers(languages=frozenset({"es"}), scripts=frozenset({"Latn"}), material="handwriting",
                   purposes=("search",), **kw)


def _step(recipe, job):
    return next(s for s in recipe["steps"] if s["job"] == job)


def test_forms_is_a_layout_choice_and_reaches_the_find_regions_step():
    layout = next(q for q in get_stage("find-regions").questions if q.key == "layout")
    assert "forms" in dict(layout.options) and not layout.read_by_a_step  # no run reads it yet (#5802)
    recipe = assemble(_answers(jobs=("find-regions",), job_answers={"layout": ["columns", "forms"]}), CARDS)
    assert _step(recipe, "find-regions")["settings"] == {"layout": ["columns", "forms"]}


def test_handwriting_and_print_on_one_page_gives_each_kind_its_own_reader_routed_by_region():
    question = next(q for q in get_stage("find-regions").questions if q.key == "mixed_writing")
    assert question.kind == "yes-no" and question.ask == "Handwriting and print on the same page?"
    assert not question.read_by_a_step  # nothing reads route_by at run time yet (#5802)
    recipe = assemble(_answers(jobs=("find-regions", "read-a-line"), job_answers={"mixed_writing": True}), CARDS)
    read = _step(recipe, "read-a-line")
    assert [r["material"] for r in read["readers"]] == ["handwriting", "print"]
    assert read["settings"]["route_by"] == "region"
    assert all(r.get("model") for r in read["readers"])


def test_without_the_answer_one_reader_and_no_routing():
    read = _step(assemble(_answers(jobs=("find-regions", "read-a-line")), CARDS), "read-a-line")
    assert "readers" not in read and "route_by" not in (read.get("settings") or {})


def test_every_step_names_its_model_with_a_link_or_says_which_answer_is_missing():
    recipe = assemble(_answers(jobs=("find-regions", "read-a-line", "find-names-tag-words")), CARDS)
    assert recipe["steps"]
    for step in recipe["steps"]:
        if isinstance(step.get("model"), dict):
            assert step["model_name"], step
            assert step["model_link"] is None or step["model_link"].startswith("https://"), step
        else:
            assert step["needs"], step  # no model known: the answer still needed, in words
    zenodo_or_hf = [s for s in recipe["steps"] if isinstance(s.get("model"), dict)
                    and ({"hf", "zenodo"} & set(s["model"]))]
    assert zenodo_or_hf and all(s["model_link"] for s in zenodo_or_hf)
