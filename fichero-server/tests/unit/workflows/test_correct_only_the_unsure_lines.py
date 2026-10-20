"""Kraken, then a cloud model for the unsure lines (`source.recipe.kraken-then-cloud-unsure-lines`, variant A).

`correct` with `only_below_confidence` = X sends the model each line Kraken was under X sure of as its own crop (line
image + Kraken's text + the language), NEVER the page; a line at or above X is not sent and its reading is untouched; a
page with no line under the bar makes no call; the step says "N of M lines sent to <model>"; a line the model gives
nothing for keeps Kraken's text and the note says so. Driven through the real review tool with a fake model, on the page
of `test_review_corrects_the_lines_5654` (three lines Kraken found and read).
"""
from __future__ import annotations

import base64
import io
import json

import pytest
from PIL import Image

from fichero_server.llm import LLMConfig
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401  (the page fixture is theirs)
    HEIGHT, KRAKEN_READS, REVIEWER, WIDTH, _counting, _lines, _readings, page)


def _kraken_was_sure(page, sure: list[float | None]) -> None:
    """Store Kraken's certainty on each line's stored readings (the rows, `ContentRepresentation`). `_readings` returns the
    API's `ReadingRead` copies: setting the value on those and saving them stored it nowhere, so every line looked
    unstated and was sent, and the failed batch was asked again line by line (6 images for 3 lines)."""
    from fichero_server.models import ContentRepresentation

    for row, value in zip(_lines(page), sure):
        for reading in page["db"].query(ContentRepresentation, segment_id=row.id):
            reading.machine_confidence = value
            page["db"].save(reading)


async def _correct(page, monkeypatch, answers: list[str | None], force: bool = False, **extra):
    """Run the review with a bar; `answers` are what the fake model says to each line it is sent, in order."""
    import fichero_server.llm as llm
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    calls: list[dict] = []

    async def model(images, prompt, config, **kw):
        calls.append({"images": list(images), "prompt": prompt})
        start = sum(len(c["images"]) for c in calls[:-1])
        return json.dumps(answers[start:start + len(images)])

    monkeypatch.setattr(llm, "vision", model)
    result = await transcribe_review(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"],
                "skip_if_artifact_exists": not force, "only_below_confidence": 0.6, "language": "es", **extra},
        state={"library_path": page["library"], "task_id": "run-correct-1"},
        llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
    assert not result.get("error"), result.get("error")
    result["calls"] = calls
    return result


def _size(data_uri: str) -> tuple[int, int]:
    return Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1]))).size


@pytest.mark.asyncio
async def test_the_model_gets_each_unsure_lines_own_crop_never_the_page(page, monkeypatch):
    first, second, third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.30, 0.50])
    before = [r.id for r in _readings(page, first)]

    result = await _correct(page, monkeypatch, ["vezino de la ciudad", "y lo firmo."])

    images = [i for c in result["calls"] for i in c["images"]]
    assert len(images) == 2, "one image for each of the 2 unsure lines"
    assert all(_size(i)[1] < HEIGHT for i in images), [_size(i) for i in images]  # a line, not the 400x300 page
    prompt = result["calls"][0]["prompt"]
    assert KRAKEN_READS[1] in prompt and KRAKEN_READS[2] in prompt and KRAKEN_READS[0] not in prompt
    assert "(in es)" in prompt
    assert _counting(page) == [KRAKEN_READS[0], "vezino de la ciudad", "y lo firmo."]
    assert [r.id for r in _readings(page, first)] == before, "the sure line is untouched"
    assert (result["lines_sent"], result["lines_total"]) == (2, 3)
    assert any("2 of 3 lines sent to mlx/" in note for note in result["notes"]), result["notes"]


@pytest.mark.asyncio
async def test_a_page_with_no_line_under_the_bar_makes_no_call(page, monkeypatch):
    _kraken_was_sure(page, [0.95, 0.90, 0.99])

    result = await _correct(page, monkeypatch, [])

    assert result["calls"] == [] and (result["lines_sent"], result["lines_total"]) == (0, 3)
    assert _counting(page) == KRAKEN_READS and not result["artifacts"]


@pytest.mark.asyncio
async def test_a_line_with_no_stated_certainty_is_sent_never_called_sure(page, monkeypatch):
    _kraken_was_sure(page, [0.95, None, 0.95])

    result = await _correct(page, monkeypatch, ["vezino de la ciudad"])

    assert sum(len(c["images"]) for c in result["calls"]) == 1
    assert (result["lines_sent"], result["lines_total"]) == (1, 3)


@pytest.mark.asyncio
async def test_a_line_the_model_gives_nothing_for_keeps_krakens_text_and_says_so(page, monkeypatch):
    _first, second, _third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.20, 0.95])

    result = await _correct(page, monkeypatch, [None])

    assert _counting(page) == KRAKEN_READS
    assert any(second.id in note and "keep their first reader's text" in note for note in result["notes"]), result["notes"]


@pytest.mark.asyncio
async def test_a_re_run_does_not_ask_again_the_lines_this_model_already_answered(page, monkeypatch):
    _kraken_was_sure(page, [0.95, 0.30, 0.50])
    first_run = await _correct(page, monkeypatch, ["vezino de la ciudad", "y lo firmo."])
    assert sum(len(c["images"]) for c in first_run["calls"]) == 2

    again = await _correct(page, monkeypatch, [])

    assert again["calls"] == [], "both unsure lines already carry this model's reading: no call, no cost"
    assert any("already answered by mlx/" in note and "not asked again" in note for note in again["notes"]), again["notes"]
    assert _counting(page) == [KRAKEN_READS[0], "vezino de la ciudad", "y lo firmo."]


@pytest.mark.asyncio
async def test_a_forced_re_run_asks_every_unsure_line_again(page, monkeypatch):
    _kraken_was_sure(page, [0.95, 0.30, 0.50])
    await _correct(page, monkeypatch, ["vezino de la ciudad", "y lo firmo."])

    again = await _correct(page, monkeypatch, ["vezino de la cibdad", "y lo firmo"], force=True)

    assert sum(len(c["images"]) for c in again["calls"]) == 2, "skip_if_artifact_exists False re-asks"


@pytest.mark.asyncio
async def test_a_line_answer_that_is_commentary_is_refused_and_the_line_keeps_krakens_text(page, monkeypatch):
    _first, second, third = _lines(page)
    _kraken_was_sure(page, [0.95, 0.30, 0.30])

    result = await _correct(page, monkeypatch, ["Let me think about this line step by step. First, I notice that the "
                                                "writing is hard to read, so I will describe my approach:",
                                                "y lo firmo."])

    assert _counting(page) == [KRAKEN_READS[0], KRAKEN_READS[1], "y lo firmo."]
    assert any(second.id in note and "was not a reading" in note for note in result["notes"]), result["notes"]


@pytest.mark.asyncio
async def test_without_the_bar_the_page_is_sent_as_before(page, monkeypatch):
    import fichero_server.llm as llm
    from tests.unit.workflows.test_review_corrects_the_lines_5654 import _review

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
