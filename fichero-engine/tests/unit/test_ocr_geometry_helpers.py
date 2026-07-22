"""Edge/regression coverage for the pure geometry helpers in ``ocr_geometry``.

The existing ``test_ocr_geometry.py`` covers the provider parsers end-to-end.
This disjoint file pins the coordinate-conversion primitives, the bbox validator
boundaries, the confidence/page coercions, coverage math, and the cloud-provider
policy gate — all pure logic, no provider calls.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fichero.media.ocr_geometry import (
    OCRCloudProviderBlocked,
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    _bbox_from_google_poly,
    _coerce_normalized_bbox,
    _confidence_0_1,
    _first_number,
    _float,
    _normalize_xywh,
    _xyxy_to_xywh,
    _zero_based_page,
    enforce_ocr_provider_policy,
    ocr_bbox_coverage,
)


# ===========================================================================
# _xyxy_to_xywh
# ===========================================================================


def test_xyxy_to_xywh_converts():
    assert _xyxy_to_xywh([10, 20, 40, 60]) == [10.0, 20.0, 30.0, 40.0]


def test_xyxy_to_xywh_reversed_gives_negative_extent():
    # Reversed corners produce a negative width/height (caught later by bbox
    # validation, not here) — documents the raw conversion.
    assert _xyxy_to_xywh([40, 60, 10, 20]) == [40.0, 60.0, -30.0, -40.0]


def test_xyxy_to_xywh_wrong_length_raises():
    with pytest.raises(ValueError):
        _xyxy_to_xywh([1, 2, 3])


# ===========================================================================
# _normalize_xywh
# ===========================================================================


def test_normalize_xywh_divides_by_page_dims():
    assert _normalize_xywh([50, 100, 50, 50], page_width=200, page_height=400) == [
        0.25,
        0.25,
        0.25,
        0.125,
    ]


@pytest.mark.parametrize("w,h", [(0, 1), (1, 0), (-1, 1)])
def test_normalize_xywh_nonpositive_dims_raise(w, h):
    with pytest.raises(ValueError):
        _normalize_xywh([1, 1, 1, 1], page_width=w, page_height=h)


# ===========================================================================
# _coerce_normalized_bbox
# ===========================================================================


def test_coerce_already_normalized_passthrough():
    assert _coerce_normalized_bbox([0.1, 0.1, 0.2, 0.2], page_width=None, page_height=None) == [
        0.1,
        0.1,
        0.2,
        0.2,
    ]


def test_coerce_pixel_with_dims_normalizes():
    assert _coerce_normalized_bbox([10, 10, 20, 20], page_width=100, page_height=100) == [
        0.1,
        0.1,
        0.2,
        0.2,
    ]


def test_coerce_pixel_without_dims_raises():
    with pytest.raises(ValueError):
        _coerce_normalized_bbox([10, 10, 20, 20], page_width=None, page_height=None)


def test_coerce_wrong_length_raises():
    with pytest.raises(ValueError):
        _coerce_normalized_bbox([1, 2, 3], page_width=None, page_height=None)


def test_coerce_tiny_pixel_box_is_read_as_normalized():
    # Documented ambiguity: values that all fall in 0..1 are treated as already
    # normalized even if they were meant as pixels. Pins the heuristic.
    assert _coerce_normalized_bbox([0, 0, 1, 1], page_width=999, page_height=999) == [
        0.0,
        0.0,
        1.0,
        1.0,
    ]


# ===========================================================================
# _confidence_0_1
# ===========================================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.9, 0.9),
        (1, 1.0),
        (85, 0.85),      # percent -> fraction
        (150, 1.0),      # >100 clamps to 1.0
        (-5, 0.0),       # negative clamps to 0.0
        (0, 0.0),
        (None, None),
        ("", None),
    ],
)
def test_confidence_scaling(value, expected):
    assert _confidence_0_1(value) == expected


# ===========================================================================
# _zero_based_page
# ===========================================================================


def test_zero_based_page_converts_one_based():
    assert _zero_based_page(5, already_zero_based=False) == 4


def test_zero_based_page_passthrough_when_already_zero_based():
    assert _zero_based_page(5, already_zero_based=True) == 5


def test_zero_based_page_none_and_zero():
    assert _zero_based_page(None) is None
    assert _zero_based_page("") is None
    # A 1-based value of 0 floors at 0 (never negative).
    assert _zero_based_page(0, already_zero_based=False) == 0


# ===========================================================================
# _first_number / _float
# ===========================================================================


def test_first_number_picks_first_present_key():
    assert _first_number({"a": None, "b": 3, "c": 9}, "a", "b", "c") == 3.0


def test_first_number_returns_zero_value_not_skipped():
    # 0 is a present value, not "missing".
    assert _first_number({"a": 0}, "a") == 0.0


def test_first_number_all_missing_returns_none():
    assert _first_number({"a": None, "b": ""}, "a", "b") is None


def test_float_coerces_none_and_strings():
    assert _float(None) == 0.0
    assert _float("0") == 0.0
    assert _float(2.5) == 2.5
    assert _float(0) == 0.0


# ===========================================================================
# OCRGeometryBox bbox validation boundaries
# ===========================================================================


def test_bbox_valid_full_page():
    box = OCRGeometryBox(text="x", bbox=[0, 0, 1, 1])
    assert box.bbox == [0.0, 0.0, 1.0, 1.0]
    assert box.level == OCRGeometryLevel.WORD  # default


def test_bbox_edge_epsilon_tolerance():
    # x + width == 1.0 exactly is within tolerance (epsilon 1.000001).
    OCRGeometryBox(text="x", bbox=[0.5, 0.5, 0.5, 0.5])


@pytest.mark.parametrize(
    "bbox",
    [
        [0, 0, 1.5, 0.5],   # value > 1
        [0.5, 0, -0.1, 0.1],  # negative width
        [0.6, 0, 0.5, 0.1],   # x + width overflows page
        [0, 0, 1],            # wrong length
        [-0.1, 0, 0.1, 0.1],  # negative coordinate
    ],
)
def test_bbox_invalid_rejected(bbox):
    with pytest.raises(ValidationError):
        OCRGeometryBox(text="x", bbox=bbox)


def test_bbox_text_coerced_from_none():
    assert OCRGeometryBox(text=None, bbox=[0, 0, 0.1, 0.1]).text == ""


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        OCRGeometryBox(text="x", bbox=[0, 0, 0.1, 0.1], bogus="nope")


# ===========================================================================
# ocr_bbox_coverage
# ===========================================================================


def test_coverage_partial():
    result = OCRGeometryResult(
        provider="p",
        text="a b c",
        boxes=[OCRGeometryBox(text="a b", bbox=[0, 0, 0.1, 0.1])],
    )
    assert ocr_bbox_coverage(result) == pytest.approx(2 / 3)


def test_coverage_clamps_to_one():
    result = OCRGeometryResult(
        provider="p",
        text="a b",
        boxes=[OCRGeometryBox(text="a b c d", bbox=[0, 0, 0.1, 0.1])],
    )
    assert ocr_bbox_coverage(result) == 1.0


def test_coverage_empty_text_is_zero():
    assert ocr_bbox_coverage(OCRGeometryResult(provider="p", text="", boxes=[])) == 0.0


# ===========================================================================
# enforce_ocr_provider_policy (cloud gate)
# ===========================================================================


@pytest.mark.parametrize("provider", ["google", "GOOGLE-VISION", "aws_textract", "azure", "amazon"])
def test_policy_blocks_cloud_when_local_only(provider):
    with pytest.raises(OCRCloudProviderBlocked):
        enforce_ocr_provider_policy(provider, local_only=True)


@pytest.mark.parametrize("provider", ["apple_vision", "tesseract_tsv", "paddleocr", "pymupdf"])
def test_policy_allows_local_providers(provider):
    enforce_ocr_provider_policy(provider, local_only=True)  # no raise


def test_policy_allows_cloud_when_not_local_only():
    enforce_ocr_provider_policy("google", local_only=False)  # no raise


# ===========================================================================
# _bbox_from_google_poly
# ===========================================================================


def test_google_poly_normalized_vertices():
    box = _bbox_from_google_poly(
        {"normalizedVertices": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.4}]},
        page_width=None,
        page_height=None,
    )
    assert box[0] == pytest.approx(0.1)
    assert box[1] == pytest.approx(0.1)
    assert box[2] == pytest.approx(0.2)  # width = 0.3 - 0.1
    assert box[3] == pytest.approx(0.3)  # height = 0.4 - 0.1


def test_google_poly_pixel_vertices_require_dims():
    with pytest.raises(ValueError):
        _bbox_from_google_poly(
            {"vertices": [{"x": 10, "y": 10}, {"x": 30, "y": 40}]},
            page_width=None,
            page_height=None,
        )


def test_google_poly_pixel_vertices_normalized_with_dims():
    box = _bbox_from_google_poly(
        {"vertices": [{"x": 10, "y": 20}, {"x": 30, "y": 60}]},
        page_width=100,
        page_height=200,
    )
    assert box == [0.1, 0.1, 0.2, 0.2]
