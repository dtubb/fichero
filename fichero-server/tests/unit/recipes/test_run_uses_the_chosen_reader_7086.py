"""The recipe runs the reader the read step shows as chosen, and Activity names it (#7086).

WHY: the owner chose PP-OCRv6 and saw "Transcribe (Kraken)" with `kraken-zenodo-21788410` in the engine log, with no
way to tell that record is PP-OCRv6. The run did use the chosen reader; Activity named only the id.
"""
from __future__ import annotations

import json

from fichero_server.recipes import runner, start
from fichero_server.recipes.start import plan_start
from fichero_server.workflows.validation import apply_run_model_override
from tests.unit.recipes.test_start_plan import LINES, READ, _recipe

PPOCR = {"zenodo": "10.5281/zenodo.21788410"}
PPOCR_ID = "kraken-zenodo-21788410"


def _read_card(plan):
    return next(r for r in plan["workflows"] if "read" in r["steps"])


def _plan_with(pin):
    recipe = _recipe(LINES, {**READ, "model": pin})
    return plan_start(recipe, stays_local=True)


def test_a_read_step_pinned_to_ppocr_gives_a_card_that_runs_that_reader():
    plan = _plan_with(PPOCR)
    assert plan["refusals"] == []
    card = _read_card(plan)
    assert (card["provider_override"], card["model_override"]) == ("kraken", PPOCR_ID)


def test_the_run_override_lands_on_the_kraken_node_of_the_workflow():
    from fichero_server.workflows.default_workflows import _load_preset_files

    card = _read_card(_plan_with(PPOCR))
    preset = next(p for p in _load_preset_files() if p.get("name") == card["workflow"])
    nodes = json.loads(json.dumps(preset["nodes"]))
    reached = apply_run_model_override(nodes, card["provider_override"], card["model_override"])
    assert reached, "no node took the chosen reader"
    configs = [n.get("config", {}) for n in nodes if n["id"] in reached]
    assert {c.get("kraken_model") for c in configs} == {PPOCR_ID}


def test_activity_names_the_reader_as_a_person_reads_it():
    card = _read_card(_plan_with(PPOCR))
    assert runner.doing_words(card) == "Reading each line with PP-OCRv6 (medium)"


def test_a_pinned_model_that_cannot_run_refuses_start_in_words_and_swaps_nothing():
    plan = _plan_with({"hf": "someone/not-a-reader", "revision": "main"})
    assert plan["workflows"] == [] or all("read" not in r["steps"] for r in plan["workflows"])
    assert plan["refusals"], "start must say why"
    assert "someone/not-a-reader" in " ".join(plan["refusals"])
    assert start._reading_run("read-a-line", {"hf": "someone/not-a-reader", "revision": "main"}) is None
