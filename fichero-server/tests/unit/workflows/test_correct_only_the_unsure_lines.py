"""Kraken, then a cloud model for the unsure lines (`source.recipe.kraken-then-cloud-unsure-lines`, variant A).

`correct` with `only_below_confidence` = X sends the model ONLY the lines Kraken was under X sure of; a line at or above
X is not sent and its reading is untouched; the step says "N of M lines sent to <model>"; a line the model cannot read
keeps Kraken's text and says why. Driven through the real review tool with a fake model, on the page of
`test_review_corrects_the_lines_5654` (three lines Kraken found and read).
"""
from __future__ import annotations

import pytest

from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401  (the page fixture is theirs)
    KRAKEN_READS, REVIEWER, _counting, _lines, _readings, _review, page)


def _kraken_was_sure(page, sure: list[float]) -> None:
    for row, value in zip(_lines(page), sure):
        for reading in _readings(page, row):
            reading.machine_confidence = value
            page["db"].save(reading)


@pytest.mark.asyncio
async def test_only_the_unsure_lines_are_sent_and_the_sure_ones_are_untouched(page, monkeypatch):
    first, second, third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.30, 0.50])
    before = {row.id: [r.id for r in _readings(page, row)] for row in (first, third)}

    result = await _review(page, monkeypatch, f"{second.id} | certain | vezino de la ciudad\n"
                                              f"{third.id} | certain | y lo firmo",
                           only_below_confidence=0.6)

    assert first.id not in result["prompt"] and second.id in result["prompt"] and third.id in result["prompt"]
    assert _counting(page)[0] == KRAKEN_READS[0] and [r.id for r in _readings(page, first)] == before[first.id]
    assert _counting(page)[1] == "vezino de la ciudad"
    assert (result["lines_sent"], result["lines_total"]) == (2, 3)
    assert any("2 of 3 lines sent to mlx/" in note for note in result["notes"]), result["notes"]


@pytest.mark.asyncio
async def test_a_line_with_no_stated_certainty_is_sent_never_called_sure(page, monkeypatch):
    first, second, third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.95, 0.95])
    for reading in _readings(page, second):
        reading.machine_confidence = None
        page["db"].save(reading)

    result = await _review(page, monkeypatch, f"{second.id} | certain | vezino de la ciudad", only_below_confidence=0.6)

    assert second.id in result["prompt"] and first.id not in result["prompt"] and third.id not in result["prompt"]
    assert (result["lines_sent"], result["lines_total"]) == (1, 3)


@pytest.mark.asyncio
async def test_a_line_the_model_cannot_read_keeps_krakens_text_and_says_why(page, monkeypatch):
    _first, second, _third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.20, 0.95])

    result = await _review(page, monkeypatch, f"{second.id} | unreadable | {KRAKEN_READS[1]} | note: bleed-through",
                           only_below_confidence=0.6)

    assert _counting(page) == KRAKEN_READS
    assert not [r for r in _readings(page, second) if r.content.lower() == "unreadable"]
    from fichero_server.models import Artifact

    artifact = page["db"].get(Artifact, result["results"][0]["artifact_id"])
    assert artifact.data["unreadable_lines"] == [second.id]


@pytest.mark.asyncio
async def test_without_the_bar_every_line_is_sent_as_before(page, monkeypatch):
    first, second, third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.30, 0.50])

    result = await _review(page, monkeypatch, f"{second.id} | certain | vezino de la ciudad")

    assert all(row.id in result["prompt"] for row in (first, second, third))
    assert "lines_sent" not in result


def test_a_correct_step_with_a_bar_reaches_the_review_node(monkeypatch):
    from fichero_server.recipes import start
    from tests.unit.recipes.test_start_plan import CLOUD_CORRECT, LINES, READ, _recipe

    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs, names=None: [])
    step = {**CLOUD_CORRECT, "settings": {"only_below_confidence": 0.6}}
    [run] = [r for r in start.plan_start(_recipe(LINES, READ, step), stays_local=False)["runs"]
             if "correct" in r["steps"]]
    assert run["tool_config"] == {"transcribe_review": {"only_below_confidence": 0.6}}
