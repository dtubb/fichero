"""Forced alignment of a KNOWN transcript onto Kraken baseline boxes.

Kraken's ``blla`` segmenter (``segment_to_geometry`` in ``llm.kraken_runtime``)
produces one polygon + baseline per text line but reads *nothing*: every
``OCRGeometryBox`` it emits has ``text=""`` and its pixel geometry parked in
``metadata["polygon_px"]`` / ``metadata["baseline_px"]``. When the page already
has a good transcript — usually a cloud pass (Gemini / Sonnet whole-page text),
not Kraken's own poor HTR — we want to hang each transcript line on its baseline
*without* running any model. That is what this module does.

Design stance (honest by default): this is line-level **forced order**
alignment. When the transcript's line count equals the baseline count the
mapping is unambiguous and one-to-one in reading order. When the counts differ,
a single dropped or split line would shift every following line onto the wrong
baseline — a wrong region is a wrong claim about the page — so we DECLINE to
align and say why, rather than emit a plausible-looking but wrong overlay. The
caller (and the historian) can then decide. See ``AlignmentStatus``.

The output is an :class:`OCRGeometryResult` in exactly the shape the reader's
region overlay already consumes, so an aligned page is a drop-in overlay source.
"""

from __future__ import annotations

from enum import StrEnum

from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryLevel,
    OCRGeometryResult,
    line_spans,
)

#: Marks text that was supplied externally and is authoritative — the geometry
#: was forced to it, it was not produced by recognition. An aligned pair with
#: this flag (and ``reviewed=True`` on the artifact) is training-ready ground
#: truth for ``ketos train``; its absence means the text is a machine guess.
GROUND_TRUTH_SOURCE = "known_transcript"


class AlignmentStatus(StrEnum):
    """Why an alignment attempt produced the boxes it did."""

    ALIGNED = "aligned"  # one-to-one order assignment, counts matched
    NO_TRANSCRIPT = "no_transcript"  # nothing to align
    NO_BASELINES = "no_baselines"  # geometry had no line boxes to align to
    COUNT_MISMATCH = "count_mismatch"  # line count != baseline count; declined


class AlignmentMethod(StrEnum):
    """How one box got its text (recorded per box in ``metadata``)."""

    FORCED_ORDER = "forced_order"
    UNMATCHED = "unmatched"


# Metadata keys written on the RESULT (not the individual boxes).
STATUS_KEY = "alignment_status"
CONFIDENCE_KEY = "alignment_confidence"
TRANSCRIPT_LINE_COUNT_KEY = "transcript_line_count"
BASELINE_COUNT_KEY = "baseline_count"
UNMATCHED_LINES_KEY = "unmatched_transcript_lines"
GROUND_TRUTH_KEY = "ground_truth_source"

# Metadata keys written on each aligned BOX.
BOX_METHOD_KEY = "alignment_method"
BOX_CONFIDENCE_KEY = "alignment_confidence"


def _ordered_line_boxes(regions: OCRGeometryResult) -> list[OCRGeometryBox]:
    """Baseline boxes in reading order.

    Kraken emits LINE-level boxes already in reading order and stamps each with
    ``metadata["line_index"]``; we sort on that index when present so a caller
    that reordered the list (or a future multi-source merge) still aligns in the
    order the segmenter meant. Non-LINE boxes (should not occur for Kraken) are
    ignored — they are not alignment targets.
    """
    line_boxes = [
        box for box in regions.boxes if box.level == OCRGeometryLevel.LINE
    ]

    def _key(item: tuple[int, OCRGeometryBox]) -> tuple[int, float]:
        fallback_index, box = item
        raw = box.metadata.get("line_index")
        index = raw if isinstance(raw, int) else fallback_index
        # Break ties (or a missing index) by vertical position, then insertion
        # order, so the sort is total and stable.
        top = box.bbox[1] if len(box.bbox) == 4 else 0.0
        return (index, top)

    return [
        box
        for _, box in sorted(enumerate(line_boxes), key=_key)
    ]


def _transcript_lines(transcript: str) -> list[tuple[int, int, str]]:
    """Non-blank logical lines as ``(char_start, char_end, text)`` triples.

    Spans index into the ORIGINAL ``transcript`` string (blank lines skipped but
    their characters still counted), so a downstream search hit resolved to a
    char span maps back to the right box, and an exported line carries its exact
    source text.
    """
    lines: list[tuple[int, int, str]] = []
    for start, end in line_spans(transcript):
        segment = transcript[start:end]
        if segment.strip():
            lines.append((start, end, segment))
    return lines


def align_transcript_to_baselines(
    transcript: str,
    regions: OCRGeometryResult,
) -> OCRGeometryResult:
    """Hang each transcript line on its Kraken baseline, in reading order.

    Returns an :class:`OCRGeometryResult` whose ``metadata`` always carries an
    :class:`AlignmentStatus` under :data:`STATUS_KEY`:

    * ``ALIGNED`` — line count matched baseline count; each box now carries its
      transcript line in ``box.text`` with ``char_start``/``char_end`` indexing
      into ``result.text`` (the full transcript). ``CONFIDENCE_KEY`` is ``1.0``.
    * ``NO_TRANSCRIPT`` / ``NO_BASELINES`` / ``COUNT_MISMATCH`` — no alignment
      was performed; the original geometry is returned unchanged (text still
      empty) and the metadata records the counts so the caller can explain the
      decline or ask the user. Nothing wrong is ever put on the page.

    This function is pure: it neither reads files nor calls any model.
    """
    ordered = _ordered_line_boxes(regions)
    lines = _transcript_lines(transcript)

    if not transcript.strip():
        return _declined(regions, AlignmentStatus.NO_TRANSCRIPT, transcript, len(ordered))
    if not ordered:
        return _declined(regions, AlignmentStatus.NO_BASELINES, transcript, 0)
    if len(lines) != len(ordered):
        return _declined(
            regions,
            AlignmentStatus.COUNT_MISMATCH,
            transcript,
            len(ordered),
            transcript_line_count=len(lines),
        )

    aligned: list[OCRGeometryBox] = []
    for box, (char_start, char_end, text) in zip(ordered, lines, strict=True):
        merged_metadata = dict(box.metadata)
        merged_metadata[BOX_METHOD_KEY] = AlignmentMethod.FORCED_ORDER.value
        merged_metadata[BOX_CONFIDENCE_KEY] = 1.0
        aligned.append(
            box.model_copy(
                update={
                    "text": text,
                    "char_start": char_start,
                    "char_end": char_end,
                    "confidence": 1.0,
                    "metadata": merged_metadata,
                }
            )
        )

    metadata = dict(regions.metadata)
    metadata.update(
        {
            STATUS_KEY: AlignmentStatus.ALIGNED.value,
            CONFIDENCE_KEY: 1.0,
            TRANSCRIPT_LINE_COUNT_KEY: len(lines),
            BASELINE_COUNT_KEY: len(ordered),
            UNMATCHED_LINES_KEY: [],
            GROUND_TRUTH_KEY: GROUND_TRUTH_SOURCE,
        }
    )
    return regions.model_copy(update={"text": transcript, "boxes": aligned, "metadata": metadata})


def _declined(
    regions: OCRGeometryResult,
    status: AlignmentStatus,
    transcript: str,
    baseline_count: int,
    *,
    transcript_line_count: int | None = None,
) -> OCRGeometryResult:
    """Return the geometry untouched, recording WHY no alignment happened.

    The overlay can still draw the empty baseline boxes; it simply has no
    transcript text to attach. Carrying the counts lets the UI say "28 lines of
    transcript, 31 baselines — alignment skipped" instead of failing silently.
    """
    lines = _transcript_lines(transcript)
    counted = transcript_line_count if transcript_line_count is not None else len(lines)
    metadata = dict(regions.metadata)
    metadata.update(
        {
            STATUS_KEY: status.value,
            CONFIDENCE_KEY: 0.0,
            TRANSCRIPT_LINE_COUNT_KEY: counted,
            BASELINE_COUNT_KEY: baseline_count,
            # On a mismatch every line is unplaced; on the empty cases there is
            # nothing to carry. Either way the tail is honest, not guessed.
            UNMATCHED_LINES_KEY: [text for _, _, text in lines]
            if status == AlignmentStatus.COUNT_MISMATCH
            else [],
        }
    )
    return regions.model_copy(update={"metadata": metadata})
