"""A review that does not tie to the page's lines is asked again line by line
(`source.job.correct-re-asks-per-line-when-it-does-not-tie`, #5720).

The page is asked whole first; the lines it left out are cut from the page and asked in batches, and a line
still unanswered fails THAT page's step rather than being guessed. The stub answers a paragraph to the page
call and JSON arrays to the line calls, so the real tool, the real re-ask and the real reading writes run.
"""
from __future__ import annotations

import json

from fichero_server.workflows.tools.transcribe_review import transcribe_review

from .test_review_corrects_the_lines_5654 import (
    KRAKEN_READS,
    REVIEWER,
    _counting,
    _lines,
    _page_text,
    _readings,
    page,  # noqa: F401  (fixture)
)

PARAGRAPH = "el dicho escrivano vezino de la ciudad y lo firmo"
REREAD = ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"]


async def _run(page, monkeypatch, line_answer):  # noqa: F811
    from fichero_server import llm
    from fichero_server.llm import LLMConfig

    calls = []

    async def reviewer(images, prompt, config, **kw):
        calls.append(len(images))
        if len(images) == 1 and "JSON array" not in prompt:
            return PARAGRAPH
        return line_answer(len(images), prompt)

    monkeypatch.setattr(llm, "vision", reviewer)
    result = await transcribe_review(
        inputs={"files": page["src"]["files"], "documents": page["src"]["documents"],
                "skip_if_artifact_exists": False},
        state={"library_path": page["library"], "task_id": "run-review-5720"},
        llm_config=LLMConfig(provider=REVIEWER[0], model=REVIEWER[1]))
    return result, calls


async def test_lines_the_page_answer_left_out_are_asked_again_and_every_line_is_tied(page, monkeypatch):  # noqa: F811
    result, calls = await _run(page, monkeypatch, lambda n, prompt: json.dumps(REREAD[:n]))

    assert calls[0] == 1 and calls[1] == 3  # the page whole, then the three lines in one batch
    assert _counting(page) == REREAD
    assert all(_readings(page, row) for row in _lines(page))
    assert _page_text(page)[0].split() == PARAGRAPH.split()
    assert not result["results"][0].get("error")


async def test_a_line_still_without_an_answer_fails_that_pages_step_and_writes_nothing(page, monkeypatch):  # noqa: F811
    before = {row.id: [r.id for r in _readings(page, row)] for row in _lines(page)}
    result, _calls = await _run(page, monkeypatch, lambda n, prompt: "I cannot read these")

    one = result["results"][0]
    assert "gave no reading for 3 of the page's 3 lines" in one["error"]
    assert f"{REVIEWER[0]}/{REVIEWER[1]}" in one["error"]
    assert {row.id: [r.id for r in _readings(page, row)] for row in _lines(page)} == before
    assert _counting(page) == KRAKEN_READS


async def test_a_request_never_exceeds_the_model_cards_lines_per_request_5722(page, monkeypatch):  # noqa: F811
    from fichero_server import llm
    from fichero_server.llm.re_ask_lines import re_ask
    from fichero_server.recipes.cards import lines_per_request_for

    assert lines_per_request_for("mlx-community/Qwen2.5-VL-3B-Instruct-4bit") == 4
    assert lines_per_request_for("mlx-community/Qwen2.5-VL-7B-Instruct-4bit") is None

    sizes = []

    async def vision(images, prompt, config, **kw):
        sizes.append(len(images))
        return json.dumps(["x"] * len(images))

    monkeypatch.setattr(llm, "vision", vision)
    document = page["src"]["files"][0]
    lines = [{"id": str(i), "text": "t", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]} for i in range(5)]
    got, missing = await re_ask(document, lines, "page", REVIEWER_CONFIG(), batch=2)
    assert sorted(sizes) == [1, 2, 2] and not missing and len(got) == 5


def REVIEWER_CONFIG():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider=REVIEWER[0], model=REVIEWER[1])
