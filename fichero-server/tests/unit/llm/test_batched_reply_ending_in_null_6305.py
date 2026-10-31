"""#6305: a batched reply that ENDS in null or an empty string is suspect (a dropped line padded at the end shifts every answer one
line early, at the right length). The batch is asked once more; a reply that still ends that way is believed (a blank last line
is real) and marked no-writing. A null in the middle, or no null, is left alone; one re-ask at most."""
from __future__ import annotations

import asyncio

from PIL import Image

from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.llm.working_lines import NO_WRITING_KEY
from fichero_server.media.ocr_geometry import OCRGeometryLevel
from tests.unit.llm.test_cloud_batch_answers_in_page_order import TEXTS, _page


def _q(items):
    return "[" + ", ".join(items) + "]"


def _t(i):
    return f'"{TEXTS[i]}"'


def _run(monkeypatch, tmp_path, batch_replies):
    path, geometry = _page(tmp_path)
    page = Image.open(path)
    by_picture = {line_reader._crop_data_uri(page, b.metadata["polygon_px"]): TEXTS[i] for i, b in enumerate(geometry.boxes)}
    asked = []
    replies = list(batch_replies)

    async def model(images, prompt, config, **_):
        asked.append(len(images))
        if len(images) == 1 and images[0] in by_picture:
            return f'["{by_picture[images[0]]}"]'
        return replies.pop(0) if len(replies) > 1 else replies[0]

    monkeypatch.setattr(llm, "vision", model)
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x"), granularity="page"))
    read = {b.metadata["segment_id"]: b.text for b in out.boxes if b.level == OCRGeometryLevel.LINE}
    return read, asked, out


def test_a_shifted_reply_padded_with_null_is_asked_again_and_the_second_reply_is_used(monkeypatch, tmp_path):
    shifted = _q([_t(1), _t(2), _t(3), "null"])
    read, asked, out = _run(monkeypatch, tmp_path, [shifted, _q([_t(0), _t(1), _t(2), _t(3)])])
    assert [read[f"s{i}"] for i in range(4)] == TEXTS
    assert asked == [4, 4]
    assert out.metadata["batches_reasked_by_trailing_null"] == 1


def test_a_genuine_trailing_null_the_reask_also_returns_is_accepted_as_no_writing(monkeypatch, tmp_path):
    reply = _q([_t(0), _t(1), _t(2), "null"])
    read, asked, out = _run(monkeypatch, tmp_path, [reply])
    assert [read[f"s{i}"] for i in range(3)] == TEXTS[:3] and "s3" not in read
    assert asked == [4, 4], "asked once more, never more than once"
    assert out.metadata[NO_WRITING_KEY] == ["s3"]


def test_an_empty_string_tail_is_treated_the_same(monkeypatch, tmp_path):
    reply = _q([_t(0), _t(1), _t(2), '""'])
    read, asked, out = _run(monkeypatch, tmp_path, [reply])
    assert "s3" not in read and asked == [4, 4]
    assert out.metadata[NO_WRITING_KEY] == ["s3"]


def test_a_reask_that_is_rejected_falls_back_to_line_by_line(monkeypatch, tmp_path):
    read, asked, _ = _run(monkeypatch, tmp_path, [_q([_t(1), _t(2), _t(3), "null"]), "not json"])
    assert [read[f"s{i}"] for i in range(4)] == TEXTS
    assert asked == [4, 4, 1, 1, 1, 1]


def test_a_null_in_the_middle_is_left_alone(monkeypatch, tmp_path):
    read, asked, out = _run(monkeypatch, tmp_path, [_q([_t(0), "null", _t(2), _t(3)])])
    assert asked == [4] and "s1" not in read
    assert out.metadata["batches_reasked_by_trailing_null"] == 0


def test_a_reply_with_no_null_is_left_alone(monkeypatch, tmp_path):
    read, asked, _ = _run(monkeypatch, tmp_path, [_q([_t(i) for i in range(4)])])
    assert asked == [4] and [read[f"s{i}"] for i in range(4)] == TEXTS


def test_the_reask_goes_through_the_real_vision_cache_to_the_model(monkeypatch, tmp_path):
    """Only the model underneath is faked: the second ask must not be a content-cache hit (a changed prompt, a different key)."""
    from langchain_core.messages import AIMessage

    path, geometry = _page(tmp_path)
    calls = []
    replies = [_q([_t(1), _t(2), _t(3), "null"]), _q([_t(i) for i in range(4)])]

    class Fake:
        async def ainvoke(self, msgs):
            calls.append(1)
            return AIMessage(content=replies[min(len(calls) - 1, 1)])

    async def ready(*a, **k):
        return None

    monkeypatch.setattr(llm, "get_langchain_model", lambda c: Fake())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    monkeypatch.setattr(llm, "record_call_usage", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_enforce_local_only_provider", lambda *a, **k: None)
    llm._LLM_RESULT_CACHE.clear()
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x", api_key="k"), granularity="page"))
    read = {b.metadata["segment_id"]: b.text for b in out.boxes if b.level == OCRGeometryLevel.LINE}
    assert len(calls) == 2, "the re-ask never reached the model"
    assert [read[f"s{i}"] for i in range(4)] == TEXTS


def test_the_reask_prompt_differs_from_the_first():
    assert line_reader.prompt_for(4, reask=True) != line_reader.prompt_for(4)


def test_the_reask_prompt_still_says_null_is_right_for_a_line_with_no_writing():
    assert "still null" in line_reader.prompt_for(4, reask=True) and "invent" in line_reader.prompt_for(4, reask=True)
