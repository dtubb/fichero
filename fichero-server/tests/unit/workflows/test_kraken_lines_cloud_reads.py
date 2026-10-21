"""Variant B (`source.recipe.kraken-lines-cloud-reads`): Kraken only finds the lines; the cloud model reads every one.

Driven through the real Transcribe tool on the page of `test_review_corrects_the_lines_5654`, with a fake cloud model.
"""
from __future__ import annotations

import json

import pytest

from tests.unit.workflows.test_every_reader_ties_to_lines_5721 import _read
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401
    KRAKEN_READS, _counting, _lines, page)

CLOUD = ("anthropic", "claude-haiku-4-5")
WORDS = ["cloud uno", "cloud dos", "cloud tres"]


@pytest.mark.asyncio
async def test_every_line_is_sent_once_and_the_page_text_is_the_models(page, monkeypatch):  # noqa: F811
    result = await _read(page, monkeypatch, provider=CLOUD[0], model=CLOUD[1], vision_mode="llm", force_ocr=True,
                         answer=lambda n, call: json.dumps(WORDS[:n]))
    # three line pictures, none twice, and the whole page ONCE beside them for context (variant B, #5894), not read
    assert result["calls"] == [len(WORDS) + 1], result["calls"]
    assert _counting(page) == WORDS and not set(_counting(page)) & set(KRAKEN_READS)
