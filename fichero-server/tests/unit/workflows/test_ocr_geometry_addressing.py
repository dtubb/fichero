"""#4309/#4418 — a transcribed line must resolve to the region it came from.

This is what separates a transcription you have to TRUST from one you can
CHECK. The tests here pin three things the previous round left unproven:

1. **Word geometry survives the first pass.** Vision computes a rect for every
   word, but it hands it back wrapped in a ``VNRectangleObservation`` rather
   than as a bare rect, and the coercion helper dropped anything it did not
   recognise. The result was a real Apple Vision run reporting line boxes and
   ZERO word boxes — geometry that already existed, discarded silently, which
   is exactly the failure #4418 names.

2. **A line resolves to a region, and a region back to its text.** One
   addressing scheme — character offsets into the artifact's content — read in
   both directions, so the two directions cannot drift apart.

3. **A pass that cannot produce geometry says so.** ``produced_nothing`` vs
   ``not_supported`` vs ``not_run``, applied to geometry. An empty box list is
   three different facts wearing one costume and only one of them means the
   page is blank.

The Apple Vision cases run the REAL on-device engine on a REAL rendered page
(it is free and local); everything else is pure-function and needs no engine.
"""
from __future__ import annotations

import sys

import pytest

from fichero_server.media.ocr_geometry import (
    GEOMETRY_REASON_KEY,
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    OCRGeometryStatus,
    attach_char_spans,
    boxes_for_span,
    geometry_status,
    geometry_unavailable,
    line_spans,
    region_for_line,
    region_for_span,
    span_at_point,
    union_bbox,
)


macos_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="Apple Vision is macOS-only"
)


# ---------------------------------------------------------------------------
# 1. Geometry survives the first pass — with the REAL engine
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rendered_page(tmp_path_factory) -> str:
    """A real raster page with two known lines of text on it."""
    from PIL import Image, ImageDraw, ImageFont

    path = tmp_path_factory.mktemp("geometry") / "page.png"
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf", 44
        )
    except OSError:  # pragma: no cover - font layout differs per machine
        font = ImageFont.load_default()
    draw.text((90, 100), "En la ciudad de Santa Fe", fill="black", font=font)
    draw.text((90, 200), "a doce dias del mes de mayo", fill="black", font=font)
    image.save(str(path))
    return str(path)


@pytest.fixture(scope="module")
def apple_geometry(rendered_page) -> OCRGeometryResult:
    from fichero_server.workflows.tools.vision_base import (
        _apple_geometry_result,
        apple_vision_ocr_with_geometry,
    )

    result = apple_vision_ocr_with_geometry(rendered_page, "es-ES")
    if not result.text.strip():  # pragma: no cover - engine unavailable
        pytest.skip("Apple Vision recognised nothing; cannot test geometry")
    geometry = _apple_geometry_result(result)
    assert geometry is not None
    return geometry


@macos_only
def test_apple_vision_word_geometry_is_not_discarded(apple_geometry):
    """Word rects come back wrapped, and used to be dropped on the floor.

    Vision returns per-word geometry as a ``VNRectangleObservation`` — an
    object that CARRIES a rect rather than being one. The coercion helper
    checked for dicts, sequences and origin/size objects, matched none of
    them, and returned None, so every word box was silently thrown away while
    the code read as if both levels were captured.
    """
    words = [b for b in apple_geometry.boxes if b.level == OCRGeometryLevel.WORD]
    lines = [b for b in apple_geometry.boxes if b.level == OCRGeometryLevel.LINE]
    assert lines, "line geometry regressed"
    assert words, "word geometry was discarded — the wrapped rect was dropped"
    # The two lines of the fixture carry 6 and 7 words.
    assert len(words) >= 10


@macos_only
def test_apple_vision_word_boxes_sit_inside_their_line(apple_geometry):
    """A word's rect must be inside its line's rect, or the flip is wrong."""
    lines = [b for b in apple_geometry.boxes if b.level == OCRGeometryLevel.LINE]
    words = [b for b in apple_geometry.boxes if b.level == OCRGeometryLevel.WORD]
    assert words, "no words to check — this test would pass vacuously"
    for word in words:
        owner = next(
            (
                line
                for line in lines
                if line.char_start is not None
                and line.char_end is not None
                and word.char_start is not None
                and line.char_start <= word.char_start
                and word.char_end <= line.char_end
            ),
            None,
        )
        assert owner is not None, f"word {word.text!r} belongs to no line"
        wx, wy, ww, wh = word.bbox
        lx, ly, lw, lh = owner.bbox
        tol = 1e-3
        assert lx - tol <= wx and wx + ww <= lx + lw + tol
        assert ly - tol <= wy and wy + wh <= ly + lh + tol


@macos_only
def test_apple_vision_word_text_matches_its_span(apple_geometry):
    """The span is the box↔text link; if it lies, nothing downstream works."""
    for box in apple_geometry.boxes:
        if box.char_start is None or box.char_end is None:
            continue
        assert apple_geometry.text[box.char_start : box.char_end] == box.text


@macos_only
def test_apple_vision_records_the_kind_of_evidence(apple_geometry):
    """Provenance is the engine AND the kind of evidence.

    A region read off a PDF text layer and a region recognised from ink are
    not equally trustworthy, and for archival work the provenance of a region
    is as material as the region itself.
    """
    assert apple_geometry.source == "apple_vision_ocr"
    assert all(box.source == "apple_vision_ocr" for box in apple_geometry.boxes)


@macos_only
def test_line_resolves_to_its_region_on_a_real_page(apple_geometry):
    """The whole point: point at a line, get the ink it was read from."""
    first = region_for_line(apple_geometry, 0)
    second = region_for_line(apple_geometry, 1)
    assert first is not None and second is not None
    # Resolution is at the finest level available — words, not the whole line.
    assert first.level == OCRGeometryLevel.WORD
    # The fixture's second line is drawn 100px below the first on an 800px
    # page, so its region must sit lower. This is the check that would catch a
    # y-axis flip, which is the easy thing to get backwards.
    assert second.bbox[1] > first.bbox[1]
    # Each region covers its own line and no more.
    assert first.bbox[1] + first.bbox[3] <= second.bbox[1] + 1e-6


@macos_only
def test_region_and_span_are_the_same_cursor_read_two_ways(apple_geometry):
    """Select text → get a region; select that region → get the text back."""
    region = region_for_line(apple_geometry, 0)
    assert region is not None
    probe = region.boxes[0]
    centre_x = probe.bbox[0] + probe.bbox[2] / 2
    centre_y = probe.bbox[1] + probe.bbox[3] / 2
    hit = span_at_point(apple_geometry, centre_x, centre_y)
    assert hit is not None
    assert hit.text == probe.text
    assert (hit.char_start, hit.char_end) == (probe.char_start, probe.char_end)


# ---------------------------------------------------------------------------
# 2. Addressing — pure functions, every producer
# ---------------------------------------------------------------------------


def _boxes(*specs) -> OCRGeometryResult:
    return OCRGeometryResult(
        text="alpha beta\ngamma delta",
        provider="test",
        boxes=[
            OCRGeometryBox(
                text=text,
                bbox=bbox,
                level=level,
                char_start=start,
                char_end=end,
            )
            for text, bbox, level, start, end in specs
        ],
    )


WORDS = _boxes(
    ("alpha", [0.1, 0.1, 0.2, 0.05], OCRGeometryLevel.WORD, 0, 5),
    ("beta", [0.35, 0.1, 0.15, 0.05], OCRGeometryLevel.WORD, 6, 10),
    ("gamma", [0.1, 0.3, 0.2, 0.05], OCRGeometryLevel.WORD, 11, 16),
    ("delta", [0.35, 0.3, 0.2, 0.05], OCRGeometryLevel.WORD, 17, 22),
)


def test_line_spans_exclude_the_newline():
    assert line_spans("alpha beta\ngamma delta") == [(0, 10), (11, 22)]


def test_region_for_line_unions_only_that_line_s_words():
    region = region_for_line(WORDS, 0)
    assert region is not None
    assert [b.text for b in region.boxes] == ["alpha", "beta"]
    assert region.bbox == pytest.approx([0.1, 0.1, 0.4, 0.05])


def test_region_for_span_is_tight_to_the_span():
    region = region_for_span(WORDS, 6, 10)
    assert region is not None
    assert [b.text for b in region.boxes] == ["beta"]
    assert region.bbox == pytest.approx([0.35, 0.1, 0.15, 0.05])


def test_span_that_cannot_be_placed_returns_none_not_the_origin():
    """An unplaceable span is not a span at (0, 0)."""
    assert region_for_span(WORDS, 900, 950) is None
    assert region_for_line(WORDS, 7) is None


def test_resolution_falls_back_to_line_level_when_words_are_absent():
    """Apple Vision and the PDF text layer disagree on granularity.

    A consumer that demanded word boxes would work against PDFs and silently
    fail against images, so resolution takes the finest level AVAILABLE.
    """
    lines_only = _boxes(
        ("alpha beta", [0.1, 0.1, 0.4, 0.05], OCRGeometryLevel.LINE, 0, 10),
        ("gamma delta", [0.1, 0.3, 0.45, 0.05], OCRGeometryLevel.LINE, 11, 22),
    )
    region = region_for_line(lines_only, 1)
    assert region is not None
    assert region.level == OCRGeometryLevel.LINE
    assert region.bbox == pytest.approx([0.1, 0.3, 0.45, 0.05])


def test_boxes_without_spans_are_excluded_not_guessed_at():
    unanchored = OCRGeometryResult(
        text="alpha beta",
        provider="test",
        boxes=[OCRGeometryBox(text="alpha", bbox=[0.1, 0.1, 0.2, 0.05])],
    )
    assert boxes_for_span(unanchored, 0, 5) == []
    assert region_for_span(unanchored, 0, 5) is None


def test_span_at_point_prefers_the_smallest_containing_box():
    """A word inside a line is the more precise answer; both contain the point."""
    mixed = _boxes(
        ("alpha beta", [0.1, 0.1, 0.4, 0.05], OCRGeometryLevel.LINE, 0, 10),
        ("alpha", [0.1, 0.1, 0.2, 0.05], OCRGeometryLevel.WORD, 0, 5),
    )
    hit = span_at_point(mixed, 0.15, 0.12)
    assert hit is not None and hit.text == "alpha"


def test_point_outside_every_box_resolves_to_nothing():
    assert span_at_point(WORDS, 0.99, 0.99) is None


def test_union_bbox_of_nothing_is_none():
    assert union_bbox([]) is None


def test_attach_char_spans_anchors_vlm_boxes_into_the_transcript():
    """A VLM returns text and boxes as two separate things.

    Without establishing the link the boxes can be drawn on the page but no
    line of the transcript resolves to one — geometry that is visible and
    un-addressable.
    """
    loose = OCRGeometryResult(
        text="alpha beta gamma",
        provider="vlm_json",
        boxes=[
            OCRGeometryBox(text="beta", bbox=[0.35, 0.1, 0.15, 0.05]),
            OCRGeometryBox(text="gamma", bbox=[0.55, 0.1, 0.2, 0.05]),
        ],
    )
    anchored = attach_char_spans(loose)
    assert [(b.char_start, b.char_end) for b in anchored.boxes] == [(6, 10), (11, 16)]
    region = region_for_span(anchored, 6, 10)
    assert region is not None and [b.text for b in region.boxes] == ["beta"]


def test_attach_char_spans_walks_forward_for_repeated_words():
    """A word repeated on the page anchors to its OWN occurrence."""
    loose = OCRGeometryResult(
        text="de la de",
        provider="vlm_json",
        boxes=[
            OCRGeometryBox(text="de", bbox=[0.1, 0.1, 0.05, 0.05]),
            OCRGeometryBox(text="de", bbox=[0.3, 0.1, 0.05, 0.05]),
        ],
    )
    anchored = attach_char_spans(loose)
    assert [(b.char_start, b.char_end) for b in anchored.boxes] == [(0, 2), (6, 8)]


def test_attach_char_spans_leaves_unfindable_text_unanchored():
    """A wrong region is a wrong claim about the page — better to have none."""
    loose = OCRGeometryResult(
        text="alpha beta",
        provider="vlm_json",
        boxes=[OCRGeometryBox(text="omega", bbox=[0.1, 0.1, 0.2, 0.05])],
    )
    anchored = attach_char_spans(loose)
    assert anchored.boxes[0].char_start is None
    assert anchored.boxes[0].char_end is None


# ---------------------------------------------------------------------------
# 3. Honest status — produced_nothing vs not_supported vs not_run
# ---------------------------------------------------------------------------


def test_nothing_recorded_reads_as_not_run_never_as_a_blank_page():
    assert geometry_status(None) is OCRGeometryStatus.NOT_RUN


def test_boxes_present_reads_as_captured():
    assert geometry_status(WORDS) is OCRGeometryStatus.CAPTURED


def test_a_provider_that_cannot_localize_says_so():
    record = geometry_unavailable(
        status=OCRGeometryStatus.NOT_SUPPORTED,
        provider="anthropic",
        model="claude-x",
        reason="anthropic/claude-x does not localize the text it reads",
    )
    assert geometry_status(record) is OCRGeometryStatus.NOT_SUPPORTED
    assert "does not localize" in record.metadata[GEOMETRY_REASON_KEY]


def test_a_boxless_record_with_no_status_is_not_evidence_of_a_blank_page():
    """Pre-contract records must degrade to the weaker true statement."""
    legacy = OCRGeometryResult(text="", provider="apple_vision", boxes=[])
    assert geometry_status(legacy) is OCRGeometryStatus.NOT_RUN


def test_geometry_unavailable_refuses_to_describe_a_captured_result():
    with pytest.raises(ValueError, match="captured"):
        geometry_unavailable(
            status=OCRGeometryStatus.CAPTURED,
            provider="apple_vision",
            reason="nope",
        )


def test_pdf_page_with_no_text_layer_says_produced_nothing():
    """A scan is not a blank page, and it is not an un-run workflow either."""
    import fitz

    from fichero_server.media.ocr_geometry import PDF_TEXT_LAYER_FLAG, from_pymupdf_page

    doc = fitz.open()
    try:
        page = doc.new_page()
        geometry = from_pymupdf_page(page, page_index=0)
    finally:
        doc.close()
    assert geometry.boxes == []
    assert geometry.metadata[PDF_TEXT_LAYER_FLAG] is False
    assert geometry_status(geometry) is OCRGeometryStatus.PRODUCED_NOTHING
    assert "no text layer" in geometry.metadata[GEOMETRY_REASON_KEY]


def test_pdf_page_with_a_text_layer_says_captured():
    import fitz

    from fichero_server.media.ocr_geometry import from_pymupdf_page

    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "alpha beta gamma")
        geometry = from_pymupdf_page(page, page_index=0)
    finally:
        doc.close()
    assert geometry_status(geometry) is OCRGeometryStatus.CAPTURED
    region = region_for_span(geometry, 0, 5)
    assert region is not None and region.boxes[0].text == "alpha"


# ---------------------------------------------------------------------------
# 4. The LLM path records WHY it produced nothing, per workflow
# ---------------------------------------------------------------------------


def test_llm_without_box_support_records_not_supported():
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import _llm_geometry_unavailable

    record = _llm_geometry_unavailable(
        LLMConfig(provider="ollama", model="qwen2.5vl"), return_boxes=False
    )
    assert geometry_status(record) is OCRGeometryStatus.NOT_SUPPORTED
    assert "ollama/qwen2.5vl" in record.metadata[GEOMETRY_REASON_KEY]


def test_llm_that_could_return_boxes_but_was_not_asked_records_not_run():
    """"Nobody asked" and "it cannot" are different facts about the run."""
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import _llm_geometry_unavailable

    record = _llm_geometry_unavailable(
        LLMConfig(provider="google", model="gemini-2.0-flash"), return_boxes=False
    )
    assert geometry_status(record) is OCRGeometryStatus.NOT_RUN
    assert "return_boxes was not enabled" in record.metadata[GEOMETRY_REASON_KEY]


def test_a_page_that_failed_records_the_failure_not_a_blank_page():
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import _llm_geometry_unavailable

    record = _llm_geometry_unavailable(
        LLMConfig(provider="google", model="gemini-2.0-flash"),
        return_boxes=True,
        reason="page 3 failed before geometry could be captured: timeout",
    )
    assert geometry_status(record) is OCRGeometryStatus.NOT_RUN
    assert "timeout" in record.metadata[GEOMETRY_REASON_KEY]


# ---------------------------------------------------------------------------
# 5. The transcribe prompt and the parser must want the same coordinate space
# ---------------------------------------------------------------------------


def test_transcribe_box_prompt_asks_for_the_space_the_parser_reads():
    """The prompt asked for pixels; the parser required 0..1 and raised.

    Any model that COMPLIED with the prompt produced a run that failed with
    "pixel bbox values require page_width and page_height". The request and
    the reader wanted different coordinate spaces (#4309).
    """
    from fichero_server.workflows.tools.transcribe import _build_prompt

    prompt = _build_prompt("es-ES", True)
    assert "FRACTIONS OF THE IMAGE" in prompt
    assert "TOP-LEFT" in prompt
    assert '"width": 100' not in prompt


def test_the_shape_the_prompt_asks_for_actually_parses():
    """Pin prompt and parser together, so they cannot drift apart again."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "text": "En la ciudad",
        "boxes": [
            {"text": "En", "bbox": [0.07, 0.13, 0.05, 0.06], "level": "word"},
            {"text": "la", "bbox": [0.13, 0.13, 0.03, 0.06], "level": "word"},
            {"text": "ciudad", "bbox": [0.17, 0.13, 0.11, 0.06], "level": "word"},
        ],
    }
    geometry = attach_char_spans(parse_vlm_geometry(payload, provider="google"))
    assert geometry_status(geometry) is OCRGeometryStatus.CAPTURED
    region = region_for_line(geometry, 0)
    assert region is not None
    assert [b.text for b in region.boxes] == ["En", "la", "ciudad"]


def test_the_old_pixel_shape_is_the_thing_that_used_to_break():
    """Regression witness: this is what a compliant model used to send."""
    from fichero_server.media.ocr_geometry import parse_vlm_geometry

    payload = {
        "text": "En",
        "boxes": [{"text": "En", "x": 0, "y": 0, "width": 100, "height": 20}],
    }
    with pytest.raises(ValueError, match="require page_width and page_height"):
        parse_vlm_geometry(payload, provider="google")
