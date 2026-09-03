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


# ---------------------------------------------------------------------------
# Gemini's 0..1000 grid (#4372, Daniel 2026-09-02)
# ---------------------------------------------------------------------------
#
# Symptom: on a manuscript page whose handwriting sits mid-page, every line
# box rendered as a thin rectangle bunched into the top ~15% of the image.
# Apple Vision and Opus boxes on the same page landed correctly. Cause: the
# reply answered the fractions prompt in Gemini's native 0..1000 grid while
# honestly naming the image's real pixel frame, so the parser read the
# coordinates as pixels and divided a 0..1000 number by a ~2500px page.


def test_gemini_0_1000_grid_is_not_read_as_pixels_of_the_declared_frame():
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1800,
        "image_height": 2500,
        "text": "En la ciudad de Santa Fe",
        "boxes": [
            # Mid-page line: y=500/1000 is the vertical centre.
            {"text": "En la ciudad de Santa Fe", "bbox": [100, 500, 800, 30],
             "level": "line"},
        ],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    x, y, w, h = geometry.boxes[0].bbox
    assert (x, y, w, h) == pytest.approx((0.1, 0.5, 0.8, 0.03))
    # The bug in one assertion: read as pixels of a 2500px page this line
    # would have landed at y=0.2, in the top fifth.
    assert y > 0.4


def test_the_parsed_frame_is_named_in_the_result_metadata():
    """A wrong reading must be inspectable, not merely visible as misplaced
    rectangles (memory: boxes must name their pixel frame)."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1800,
        "image_height": 2500,
        "boxes": [{"text": "hola", "bbox": [100, 500, 800, 30], "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    assert geometry.metadata["source_coordinate_space"] == "normalized_1000"
    assert geometry.metadata["declared_frame"] == [1800.0, 2500.0]
    assert geometry.boxes[0].metadata["parsed_from"] == "normalized_1000"


def test_gemini_fractions_reply_still_reads_as_fractions():
    """The grid rule must not touch a reply that obeyed the prompt."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1800,
        "image_height": 2500,
        "boxes": [{"text": "hola", "bbox": [0.1, 0.5, 0.8, 0.03], "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    assert geometry.metadata["source_coordinate_space"] == "normalized"
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.5, 0.8, 0.03])


def test_gemini_values_above_1000_are_still_pixels():
    """Bigger than the grid can express — the pixel reading is the only one."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 2000,
        "image_height": 3000,
        "boxes": [{"text": "hola", "bbox": [200, 1500, 1600, 90], "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    assert geometry.metadata["source_coordinate_space"] == "pixel"
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.5, 0.8, 0.03])


def test_non_gemini_pixel_reply_is_unaffected():
    """Qwen/other models that send honest pixels keep the pixel reading."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1000,
        "image_height": 500,
        "boxes": [{"text": "En la ciudad", "bbox": [100, 50, 400, 25],
                   "level": "line"}],
    }
    geometry = parse_vlm_geometry(payload, provider="openrouter", model="qwen/qwen2-vl")
    assert geometry.metadata["source_coordinate_space"] == "pixel"
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.1, 0.4, 0.05])


def test_gemini_small_frame_keeps_the_pixel_reading():
    """When the declared frame is <=1024 the two readings nearly coincide;
    trust what the model said rather than overriding it."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1000,
        "image_height": 500,
        "boxes": [{"text": "En la ciudad", "bbox": [100, 50, 400, 25],
                   "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    assert geometry.metadata["source_coordinate_space"] == "pixel"
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.1, 0.4, 0.05])


def test_geminis_own_box_2d_key_is_ymin_xmin_ymax_xmax():
    """Gemini's documented shape. Read as [x1, y1, x2, y2] every box would
    be transposed onto the wrong axis."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "image_width": 1800,
        "image_height": 2500,
        # ymin=500, xmin=100, ymax=530, xmax=900 → x=.1 y=.5 w=.8 h=.03
        "boxes": [{"text": "hola", "box_2d": [500, 100, 530, 900],
                   "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="openrouter", model="google/gemini-3.1-flash-lite"
    )
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.5, 0.8, 0.03])


def test_gemini_grid_without_a_declared_frame_is_read_not_rejected():
    """A reply that omits image_width/image_height used to raise 'pixel bbox
    values require page_width and page_height' and lose the whole page."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "boxes": [{"text": "hola", "bbox": [100, 500, 800, 30], "level": "line"}],
    }
    geometry = parse_vlm_geometry(
        payload, provider="google", model="gemini-3.1-flash-lite"
    )
    assert geometry.boxes[0].bbox == pytest.approx([0.1, 0.5, 0.8, 0.03])
