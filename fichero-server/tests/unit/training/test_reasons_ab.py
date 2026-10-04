"""The reasons A/B (#4642, `distill.reasoning.ab-decides`): measured on held-out checked lines, decided by
the noise band, written on the students' cards either way.

The contenders are stand-ins whose answers are known (the spec's "pinned with known outcomes"); the
held-out lines, the line pictures, the one CER, the decision and the cards are real.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest
from PIL import Image

from fichero_server.llm.line_reader import _crop_data_uri
from fichero_server.training import reasons_ab
from fichero_server.training.reasons import checked_lines
from fichero_server.training.reasons_ab import Contender, Score, decide
from tests.unit.training.test_palaeography_reasons import CHECKED, no_scheduler, project  # noqa: F401, F811 (fixtures)


def _score(label, arm, cer, role="student", reasoning=True):
    s = Score(label, f"fichero-trained/{label}", arm, reasoning, role)
    s.char_edits, s.chars, s.lines = round(cer * 10000), 10000, 100
    return s


def test_a_reasoning_student_is_adopted_only_beyond_the_noise_band():
    """WHY: a gain smaller than the noise band (0.5 CER points) is not evidence that reasons help, and a
    reasoning student is slower at every page it reads; and the teacher, however good, is never the
    answer-only student the reasoning students are measured against."""
    result = decide([_score("teacher", "answer", 0.01, role="teacher"), _score("a", "answer", 0.05),
                     _score("why", "why", 0.04), _score("think", "thinking", 0.047),
                     _score("why (no reasoning)", "why", 0.03, reasoning=False)])
    assert result["verdicts"]["why"]["adopted"] and result["verdicts"]["why"]["against"] == "a"
    assert not result["verdicts"]["think"]["adopted"] and "noise band" in result["verdicts"]["think"]["why"]
    assert set(result["verdicts"]) == {"why", "think"}


def test_the_ab_reads_the_held_out_lines_as_each_contender_was_trained_and_writes_the_cards(db, project, monkeypatch,  # noqa: F811
                                                                                           tmp_path):
    """WHY: a student asked differently from how it was trained is measured on the wrong task; the
    reasoning student must also be measured with its reasoning off (at a million pages that is the
    cost); and the result must reach both cards whatever it says."""
    from fichero_server.llm import mlx_model_store as store_module
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, MLXModelStore

    store = MLXModelStore(root=tmp_path / "mlx")
    monkeypatch.setattr(store_module, "get_mlx_model_store", lambda: store)
    for name in ("answer-only", "with-why"):
        store.trained_dir(f"fichero-trained/{name}").mkdir(parents=True)
        (store.trained_dir(f"fichero-trained/{name}") / TRAINED_CARD).write_text("{}")

    folder, kept, test = project
    lines, photos, _ = checked_lines(db, scope_ids=[test.id], checked=CHECKED)
    blank = Image.open(photos[test.id])  # a blank page makes every line picture the same: give it texture
    Image.frombytes("RGB", blank.size, os.urandom(blank.width * blank.height * 3)).save(photos[test.id], format="PNG")
    page = Image.open(photos[test.id])
    truth = {_crop_data_uri(page, line.polygon): line.checked for line in lines}
    asked = []

    async def ask(contender, images, prompt):
        asked.append((contender.label, prompt))
        text = truth[images[0]]
        if contender.label == "answer-only":
            return json.dumps([text + "x"])  # one wrong letter on every line
        if contender.arm == "why" and contender.reasoning:
            return json.dumps([{"letterforms": "", "abbreviations": [], "uncertain": [{"reading": text}],
                                "text": text}])
        return json.dumps([text])

    contenders = [Contender("answer-only", "omlx", "fichero-trained/answer-only"),
                  Contender("with-why", "omlx", "fichero-trained/with-why", arm="why"),
                  Contender("teacher", "openrouter", "google/gemini-3-flash-preview", role="teacher")]
    result = asyncio.run(reasons_ab.run_ab(db, checked=CHECKED, held_out_ids=[test.id], contenders=contenders,
                                           ask=ask))

    scores = {s["label"]: s for s in result["scores"]}
    assert scores["with-why"]["cer"] == 0 and scores["answer-only"]["cer"] > 0.005
    assert scores["with-why (no reasoning)"]["arm"] == "why" and not scores["with-why (no reasoning)"]["reasoning"]
    no_reasoning_prompts = {p for label, p in asked if label == "with-why (no reasoning)"}
    why_prompts = {p for label, p in asked if label == "with-why"}
    assert no_reasoning_prompts.isdisjoint(why_prompts) and "letterforms" in next(iter(why_prompts))
    assert scores["with-why"]["uncertain"]["flagged"] == len(lines)
    assert result["verdicts"]["with-why"]["adopted"]
    assert sorted(result["cards"]) == ["fichero-trained/answer-only", "fichero-trained/with-why"]
    card = json.loads((store.trained_dir("fichero-trained/answer-only") / TRAINED_CARD).read_text())
    assert card["reasons_ab"][0]["verdicts"]["with-why"]["adopted"] and card["reasons_ab"][0]["held_out"] == [test.id]


def test_the_ab_refuses_without_held_out_pages(db):
    """WHY: measured on pages an arm trained on, the A/B would reward memorising."""
    with pytest.raises(ValueError, match="held-out"):
        asyncio.run(reasons_ab.run_ab(db, checked=CHECKED, held_out_ids=[], contenders=[]))


def test_the_ab_is_a_job_on_the_remote_lane_and_the_api_refuses_without_held_out_pages(client):
    """WHY: the refusal must reach the app, CLI and MCP as a sentence; the measurement waits on model
    servers and must not hold the local ML lane."""
    from fichero_server.execution import jobs
    from fichero_server.training import reasons_job

    two = [{"label": "a", "provider": "omlx", "model": "m"}, {"label": "b", "provider": "omlx", "model": "n"}]
    r = client.post("/api/training/reasons-ab", json={"checked": "c", "held_out_ids": [], "contenders": two})
    assert r.status_code == 422 and "held-out" in r.json()["detail"]
    assert client.get("/api/training/reasons-ab/nope").status_code == 404
    reasons_job.register_job_kinds()
    assert jobs.KINDS[reasons_job.KIND_AB].lane == "remote"
