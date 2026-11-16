"""`source.disagree.person-chooses-the-readers` (#6121): the person picks the readers Find where the readers disagree compares.

Spec: docs/contributor_manual/specs/source/readings-and-apparatus.md. The choice replaces the step's reader set, never adds to it,
and the same model is never listed or compared twice.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes.assemble import Card, _disagree_step
from fichero_server.recipes.bakeoff import apply_project_overrides
from fichero_server.recipes.start import DISAGREE_JOB, use_readers

NOW = "2026-10-26T00:00:00+00:00"
GEMINI = {"cloud": "openrouter", "model": "google/gemini-3.1-flash-lite"}
KRAKEN = {"zenodo": "10.5281/zenodo.13788177"}
QWEN = {"hf": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit", "revision": "main"}


def _card(cid, pin, jobs=("read-a-page",), runs_on="this-mac", note=""):
    return Card(id=cid, pin=pin, jobs=frozenset(jobs), scripts=None, languages=None, material=frozenset(),
                runs_on=runs_on, note=note or cid)


def _recipe():
    return {"fichero_recipe": 1, "id": "t/d", "version": "0.1.0", "title": "t", "overrides": [], "steps": [
        {"id": "lines", "job": "find-lines", "model": {"kraken": "blla"}},
        {"id": "read", "job": "read-a-page", "model": GEMINI},
        {"id": "doubt", "job": DISAGREE_JOB, "model": {"builtin": "reader-comparison"}, "built_in": True,
         "settings": {"readers": [QWEN]}}]}


def _step(recipe):
    return next(s for s in recipe["steps"] if s["job"] == DISAGREE_JOB)


def test_the_choice_replaces_the_reader_set_and_survives_assembling_again():
    a, b = _card("a", GEMINI, runs_on="cloud:openrouter"), _card("b", KRAKEN, ("read-a-line",))
    recipe = use_readers(_recipe(), "doubt", [a, b], now=NOW)
    assert _step(recipe)["settings"]["readers"] == [GEMINI, KRAKEN], "the rules' own reader (Qwen) is gone"
    again = apply_project_overrides(_recipe() | {"overrides": recipe["overrides"]}, [a, b])
    assert _step(again)["settings"]["readers"] == [GEMINI, KRAKEN]


def test_the_same_model_twice_counts_once_and_one_reader_is_refused():
    a, dup = _card("a", GEMINI, runs_on="cloud:openrouter"), _card("a2", dict(GEMINI), runs_on="cloud:openrouter")
    with pytest.raises(ValueError, match="two or more different readers"):
        use_readers(_recipe(), "doubt", [a, dup], now=NOW)


def test_a_card_that_does_not_read_is_refused_and_so_is_another_step():
    a, spacy = _card("a", GEMINI, runs_on="cloud:openrouter"), _card("s", {"spacy": "x"}, ("find-names-tag-words",))
    with pytest.raises(ValueError, match="does not read"):
        use_readers(_recipe(), "doubt", [a, spacy], now=NOW)
    with pytest.raises(ValueError, match="not a Find where the readers disagree step"):
        use_readers(_recipe(), "read", [a, _card("b", KRAKEN, ("read-a-line",))], now=NOW)


def test_the_sentence_names_each_model_once():
    steps = [{"id": "read", "job": "read-a-page", "model": GEMINI, "card": {"note": "Gemini"}},
             {"id": "fix", "job": "correct", "model": GEMINI, "card": {"note": "Gemini"}},
             {"id": "k", "job": "read-a-line", "model": KRAKEN, "card": {"note": "Kraken"}}]
    assert _disagree_step(steps)["compares"] == ["Gemini", "Kraken"]
