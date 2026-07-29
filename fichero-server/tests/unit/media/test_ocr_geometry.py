"""Unit tests for provider-neutral OCR geometry contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fichero_server.media.ocr_geometry import (
    OCRCloudProviderBlocked,
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    enforce_ocr_provider_policy,
    from_apple_vision_result,
    ocr_bbox_coverage,
    parse_aws_textract_response,
    parse_google_vision_response,
    parse_tesseract_tsv,
    parse_vlm_geometry,
)
from fichero_server.workflows.tools.vision_base import VisionOCRBox, VisionOCRResult


def test_apple_vision_geometry_maps_to_shared_contract():
    apple_result = VisionOCRResult(
        text="Hello world",
        line_boxes=[
            VisionOCRBox(
                text="Hello world",
                bbox=[0.1, 0.2, 0.7, 0.1],
                confidence=0.91,
                page_index=2,
            )
        ],
        word_boxes=[
            VisionOCRBox(
                text="Hello",
                bbox=[0.1, 0.2, 0.3, 0.1],
                confidence=0.91,
                page_index=2,
            ),
            VisionOCRBox(
                text="world",
                bbox=[0.5, 0.2, 0.3, 0.1],
                confidence=0.89,
                page_index=2,
            ),
        ],
    )

    result = from_apple_vision_result(apple_result, source="page.png")

    assert result == OCRGeometryResult(
        text="Hello world",
        provider="apple_vision",
        model="VNRecognizeTextRequest",
        source="page.png",
        boxes=[
            OCRGeometryBox(
                text="Hello world",
                bbox=[0.1, 0.2, 0.7, 0.1],
                level=OCRGeometryLevel.LINE,
                confidence=0.91,
                page_index=2,
                provider="apple_vision",
                model="VNRecognizeTextRequest",
                source="page.png",
            ),
            OCRGeometryBox(
                text="Hello",
                bbox=[0.1, 0.2, 0.3, 0.1],
                level=OCRGeometryLevel.WORD,
                confidence=0.91,
                page_index=2,
                provider="apple_vision",
                model="VNRecognizeTextRequest",
                source="page.png",
            ),
            OCRGeometryBox(
                text="world",
                bbox=[0.5, 0.2, 0.3, 0.1],
                level=OCRGeometryLevel.WORD,
                confidence=0.89,
                page_index=2,
                provider="apple_vision",
                model="VNRecognizeTextRequest",
                source="page.png",
            ),
        ],
    )


def test_vlm_qwen_style_json_boxes_parse_with_pixel_bbox():
    payload = {
        "text": "Nóvita Enero",
        "image_width": 1000,
        "image_height": 2000,
        "boxes": [
            {
                "text": "Nóvita",
                "bbox_2d": [100, 200, 300, 260],
                "confidence": 0.8,
                "page_index": 0,
                "level": "word",
            },
            {
                "text": "Enero",
                "bbox": [350, 200, 120, 60],
                "score": 75,
                "page_index": 0,
                "level": "word",
            },
        ],
    }

    result = parse_vlm_geometry(
        payload,
        provider="qwen",
        model="Qwen3-VL-8B",
    )

    assert result.provider == "qwen"
    assert result.model == "Qwen3-VL-8B"
    assert result.text == "Nóvita Enero"
    assert result.boxes[0].bbox == [0.1, 0.1, 0.2, 0.03]
    assert result.boxes[0].coordinate_space == "pixel_xyxy"
    assert result.boxes[1].bbox == [0.35, 0.1, 0.12, 0.03]
    assert result.boxes[1].confidence == 0.75


def test_vlm_json_rejects_malformed_or_unnormalized_boxes():
    with pytest.raises(ValueError, match="boxes list"):
        parse_vlm_geometry({"text": "missing boxes"})

    with pytest.raises(ValueError, match="pixel bbox values require"):
        parse_vlm_geometry({"boxes": [{"text": "bad", "bbox": [10, 20, 30, 40]}]})

    with pytest.raises(ValidationError, match="extends outside"):
        parse_vlm_geometry({"boxes": [{"text": "bad", "bbox": [0.9, 0.9, 0.2, 0.2]}]})


def test_google_vision_text_annotations_parse_normalized_vertices():
    response = {
        "textAnnotations": [
            {"description": "Hello world"},
            {
                "description": "Hello",
                "boundingPoly": {
                    "normalizedVertices": [
                        {"x": 0.1, "y": 0.2},
                        {"x": 0.3, "y": 0.2},
                        {"x": 0.3, "y": 0.25},
                        {"x": 0.1, "y": 0.25},
                    ]
                },
            },
        ]
    }

    result = parse_google_vision_response(response)

    assert result.text == "Hello world"
    assert result.provider == "google_vision"
    assert result.boxes[0].text == "Hello"
    assert result.boxes[0].bbox == [0.1, 0.2, 0.19999999999999998, 0.04999999999999999]


def test_aws_textract_blocks_parse_lines_and_words():
    response = {
        "Blocks": [
            {
                "BlockType": "LINE",
                "Text": "Hello world",
                "Confidence": 98.0,
                "Page": 1,
                "Geometry": {
                    "BoundingBox": {
                        "Left": 0.1,
                        "Top": 0.2,
                        "Width": 0.6,
                        "Height": 0.05,
                    }
                },
            },
            {
                "BlockType": "WORD",
                "Text": "Hello",
                "Confidence": 97,
                "Page": 1,
                "Geometry": {
                    "BoundingBox": {
                        "Left": 0.1,
                        "Top": 0.2,
                        "Width": 0.2,
                        "Height": 0.05,
                    }
                },
            },
        ]
    }

    result = parse_aws_textract_response(response)

    assert result.text == "Hello world"
    assert [box.level for box in result.boxes] == [
        OCRGeometryLevel.LINE,
        OCRGeometryLevel.WORD,
    ]
    assert result.boxes[0].confidence == 0.98
    assert result.boxes[0].page_index == 0


def test_tesseract_tsv_parses_local_ocr_word_boxes():
    tsv = "\n".join(
        [
            "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t100\t200\t50\t20\t92\tHello",
            "5\t1\t160\t200\t50\t20\t88\tworld",
            "5\t1\t0\t0\t0\t0\t-1\t",
        ]
    )

    result = parse_tesseract_tsv(tsv, page_width=1000, page_height=2000)

    assert result.provider == "tesseract_tsv"
    assert result.text == "Hello world"
    assert result.boxes[0].bbox == [0.1, 0.1, 0.05, 0.01]
    assert result.boxes[1].confidence == 0.88


def test_local_only_blocks_cloud_ocr_providers_and_allows_local():
    for provider in ("google", "aws_textract", "azure_document_intelligence"):
        with pytest.raises(OCRCloudProviderBlocked):
            enforce_ocr_provider_policy(provider, local_only=True)

    enforce_ocr_provider_policy("apple_vision", local_only=True)
    enforce_ocr_provider_policy("tesseract_tsv", local_only=True)
    enforce_ocr_provider_policy("google", local_only=False)


def test_bbox_coverage_scores_words_with_geometry():
    result = OCRGeometryResult(
        text="one two three",
        provider="test",
        boxes=[
            OCRGeometryBox(text="one", bbox=[0.1, 0.1, 0.1, 0.1]),
            OCRGeometryBox(text="two", bbox=[0.2, 0.1, 0.1, 0.1]),
        ],
    )

    assert ocr_bbox_coverage(result) == pytest.approx(2 / 3)
