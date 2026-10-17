"""A model's null answer for a line stores no text (#5447), tested to the spec:
`source.lines.null-is-no-text` (docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: on SM_NPQ_C01_005 boxes 42-43 stored the four-letter text `null`: the model answered the STRING "null"
(a quoted word, not JSON null), and the Order tab, exports and the training set took it for the line's reading.
The model call is stubbed at `vision`; the parse and the page assembly are the engine's own.
"""
from __future__ import annotations

import pytest
from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
)
from PIL import Image


def _lines(n: int) -> OCRGeometryResult:
    boxes = [OCRGeometryBox(text="", bbox=[0, i / n, 1, 1 / n], level=OCRGeometryLevel.LINE,
                            provider="kraken", model="blla", source="kraken-blla",
                            metadata={"polygon_px": [[0, i * 8], [32, i * 8], [32, i * 8 + 8], [0, i * 8 + 8]]})
             for i in range(n)]
    return OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes, source="kraken-blla")


@pytest.mark.parametrize("answer", ['["null"]', '[" Null "]', '["NULL"]', "[null]", '[""]'])
def test_the_word_null_or_a_json_null_is_no_text(answer):
    assert line_reader.parse_answer(answer, 1) == [None]


def test_the_word_null_inside_a_line_is_kept_and_other_scripts_pass_through():
    got = line_reader.parse_answer('["null y void", "nullius", "\u0721\u0720\u071f\u0710", "\u7a7a"]', 4)
    assert got == ["null y void", "nullius", "\u0721\u0720\u071f\u0710", "\u7a7a"]


@pytest.mark.asyncio
async def test_a_line_the_model_answers_null_for_has_no_reading(tmp_path, monkeypatch):
    page = tmp_path / "page.png"
    Image.new("RGB", (32, 16), "white").save(page)
    monkeypatch.setattr(line_reader, "lines_per_call", lambda config: 1)
    for raw in ['["null"]', "null", '["null', "[null]"]:
        async def model(images, prompt, config, _raw=raw, **_):
            return _raw

        monkeypatch.setattr(llm, "vision", model)
        result = await line_reader.read_lines(str(page), _lines(2), LLMConfig(provider="omlx", model="student"))

        assert "null" not in result.text.lower(), raw
        assert [b.text for b in result.boxes if b.level == OCRGeometryLevel.LINE and b.text] == [], raw
