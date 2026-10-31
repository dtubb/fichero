"""#6304: a rejected batch reply is logged by reason (counts only). Nothing of it is kept: a reply that is not JSON, not an array,
of the wrong length or with an element that is not text or null may have shifted its lines, so it is asked again in full and no
text lands on a line it was not cut from."""
from __future__ import annotations

import asyncio
import logging

import pytest
from PIL import Image

from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.llm.working_lines import NO_WRITING_KEY
from fichero_server.media.ocr_geometry import OCRGeometryLevel
from tests.unit.llm.test_cloud_batch_answers_in_page_order import TEXTS, _page


def _run(monkeypatch, tmp_path, batch_reply, single_reply=None, page_context=None, full=False):
    path, geometry = _page(tmp_path)
    page = Image.open(path)
    by_picture = {line_reader._crop_data_uri(page, b.metadata["polygon_px"]): TEXTS[i] for i, b in enumerate(geometry.boxes)}
    asked = []  # the number of pictures in each call

    async def model(images, prompt, config, **_):
        asked.append(len(images))
        if len(images) == 1 and images[0] in by_picture:
            if single_reply and by_picture[images[0]] in single_reply:
                return single_reply[by_picture[images[0]]]
            return f'["{by_picture[images[0]]}"]'
        return batch_reply

    monkeypatch.setattr(llm, "vision", model)
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x"), granularity="page", page_context=page_context))
    if full:
        return out, asked
    return {b.metadata["segment_id"]: b.text for b in out.boxes if b.level == OCRGeometryLevel.LINE}, asked


def _quoted(items):
    return "[" + ", ".join(items) + "]"


@pytest.mark.parametrize("reply", [
    _quoted([f'"{TEXTS[1]}"', f'"{TEXTS[2]}"', f'"{TEXTS[3]}"', "0"]),  # the first line dropped, a 0 padding the end
    _quoted([f'"{TEXTS[0]}"', f'"{TEXTS[2]}"', f'"{TEXTS[3]}"', "0"]),  # the second line dropped
    _quoted([f'"{TEXTS[0]}"', "42", f'"{TEXTS[2]}"', '{"text": "x"}']),
])
def test_a_reply_with_an_element_that_is_not_text_is_asked_again_in_full_with_no_wrong_line(monkeypatch, tmp_path, caplog, reply):
    caplog.set_level(logging.WARNING)
    read, asked = _run(monkeypatch, tmp_path, reply)
    assert [read[f"s{i}"] for i in range(4)] == TEXTS, "0 lines carrying another line's text"
    assert asked == [4, 1, 1, 1, 1]
    assert "neither text nor null" in caplog.text


def test_a_line_whose_reask_fails_is_not_marked_as_looked_at(monkeypatch, tmp_path):
    out, _ = _run(monkeypatch, tmp_path, '["x"', single_reply={TEXTS[1]: "not an array"}, full=True)
    by_id = {b.metadata["segment_id"]: b.text for b in out.boxes if b.level == OCRGeometryLevel.LINE}
    assert sorted(by_id) == ["s0", "s2", "s3"]
    assert "s1" not in out.metadata[NO_WRITING_KEY], "an unanswered re-ask is a failed read, not a line with no writing"


def test_the_order_checks_single_answers_are_reused_in_the_full_reask(monkeypatch, tmp_path):
    scrambled = _quoted([f'"{t}"' for t in TEXTS[2:] + TEXTS[:2]])
    read, asked = _run(monkeypatch, tmp_path, scrambled, page_context=True)
    assert [read[f"s{i}"] for i in range(4)] == TEXTS
    assert asked == [5, 1, 1, 1, 1], "the batch with the page, the first and last line alone as the check, then only the two others"


@pytest.mark.parametrize("reply,why", [
    (_quoted([f'"{t}"' for t in TEXTS[:3]]), "wrong length"),  # a dropped line: every later one may sit a line too early
    (_quoted([f'"{t}"' for t in TEXTS] + ['"extra"']), "wrong length"),
    ('["Pedro Alvarado vive', "not JSON"),  # cut off
    ('{"lines": []}', "not an array"),
])
def test_a_reply_not_matched_by_position_is_asked_again_in_full_and_logged(monkeypatch, tmp_path, caplog, reply, why):
    caplog.set_level(logging.WARNING)
    read, asked = _run(monkeypatch, tmp_path, reply)
    assert [read[f"s{i}"] for i in range(4)] == TEXTS
    assert asked == [4, 1, 1, 1, 1]
    assert why in caplog.text and "4 lines asked" in caplog.text
    assert TEXTS[0] not in caplog.text, "the reply's text is never logged"
