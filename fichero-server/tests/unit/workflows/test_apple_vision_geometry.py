"""Unit tests for Apple Vision OCR geometry extraction.

These tests use fake observation/candidate objects so they do not need the
real Vision framework.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox,
    VisionOCRResult,
    apple_vision_ocr,
    _vision_geometry_from_results,
)


def _rect(x: float, y: float, width: float, height: float) -> SimpleNamespace:
    return SimpleNamespace(
        origin=SimpleNamespace(x=x, y=y),
        size=SimpleNamespace(width=width, height=height),
    )


class FakeCandidate:
    def __init__(self, text: str, *, confidence: float | None = None, boxes: dict[tuple[int, int], object] | None = None):
        self._text = text
        self._confidence = confidence
        self._boxes = boxes or {}

    def string(self):
        return self._text

    def confidence(self):
        return self._confidence

    def boundingBoxForRange_error_(self, text_range, _error=None):
        return self._boxes.get(tuple(text_range))


class FakeObservation:
    def __init__(self, bbox: object, candidate: FakeCandidate):
        self._bbox = bbox
        self._candidate = candidate

    def boundingBox(self):
        return self._bbox

    def topCandidates_(self, count: int):
        return [self._candidate][:count]


def test_geometry_preserves_line_and_word_boxes_with_page_index():
    candidate = FakeCandidate(
        "Hello world",
        confidence=0.91,
        boxes={
            (0, 5): _rect(0.10, 0.20, 0.30, 0.10),
            (6, 5): _rect(0.45, 0.20, 0.25, 0.10),
        },
    )
    observation = FakeObservation(_rect(0.05, 0.18, 0.70, 0.16), candidate)

    result = _vision_geometry_from_results([observation], page_index=2)

    # Bboxes are flipped from Vision's bottom-left origin to the shared
    # top-left contract (y_top = 1 - y - h), and every box carries its char
    # span into the page text (#4309).
    assert result == VisionOCRResult(
        text="Hello world",
        line_boxes=[
            VisionOCRBox(
                text="Hello world",
                bbox=[0.05, 1.0 - 0.18 - 0.16, 0.70, 0.16],
                confidence=0.91,
                page_index=2,
                char_start=0,
                char_end=11,
            )
        ],
        word_boxes=[
            VisionOCRBox(
                text="Hello",
                bbox=[0.10, 1.0 - 0.20 - 0.10, 0.30, 0.10],
                confidence=0.91,
                page_index=2,
                char_start=0,
                char_end=5,
            ),
            VisionOCRBox(
                text="world",
                bbox=[0.45, 1.0 - 0.20 - 0.10, 0.25, 0.10],
                confidence=0.91,
                page_index=2,
                char_start=6,
                char_end=11,
            ),
        ],
    )


def test_geometry_retains_text_when_confidence_and_word_boxes_are_missing():
    candidate = FakeCandidate("No geometry")
    observation = FakeObservation((0.2, 0.3, 0.4, 0.5), candidate)

    result = _vision_geometry_from_results([observation])

    assert result.text == "No geometry"
    assert result.line_boxes == [
        VisionOCRBox(
            text="No geometry",
            bbox=[0.2, 1.0 - 0.3 - 0.5, 0.4, 0.5],
            confidence=None,
            page_index=None,
            char_start=0,
            char_end=11,
        )
    ]
    assert result.word_boxes == []


def test_plain_text_wrapper_keeps_compatibility():
    expected = VisionOCRResult(
        text="Preserved text",
        line_boxes=[],
        word_boxes=[],
    )

    with patch(
        "fichero_server.workflows.tools.vision_base.apple_vision_ocr_with_geometry",
        return_value=expected,
    ):
        assert apple_vision_ocr("/tmp/fake.png") == "Preserved text"
