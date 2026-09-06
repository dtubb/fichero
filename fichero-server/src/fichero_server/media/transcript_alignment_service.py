"""Glue between the pure alignment core and the artifact/document store.

:mod:`transcript_alignment` is deliberately pure (geometry in, geometry out).
This module is where alignment meets the database: resolve a page's known
transcript, run the forced alignment, and — only when it actually aligned —
build the ``aligned_transcript`` artifact both the inspector one-click action
and the ``align_transcript`` workflow node persist. Kept out of the pure module
so ``media.ocr_geometry`` (which ``models`` imports) stays free of a models
import cycle.
"""

from __future__ import annotations

from fichero_server.media.ocr_geometry import OCRGeometryResult
from fichero_server.media.transcript_alignment import (
    BASELINE_COUNT_KEY,
    CONFIDENCE_KEY,
    GROUND_TRUTH_KEY,
    STATUS_KEY,
    TRANSCRIPT_LINE_COUNT_KEY,
    UNMATCHED_LINES_KEY,
    AlignmentStatus,
    align_transcript_to_baselines,
)
from fichero_server.models import Artifact, Document

#: What the aligned pair is filed as — distinct from ``regions`` (geometry, no
#: text) and ``transcription`` (text from recognition). Signals: geometry came
#: from segmentation, text came from a known transcript, joined by forced
#: alignment. Must also be listed in the Swift ``OCRGeometrySelection`` ladder
#: or the overlay will never show it.
ALIGNED_ARTIFACT_TYPE = "aligned_transcript"


def resolve_transcript(db: object, document_id: str) -> str | None:
    """The page's known transcript, or ``None`` if it has none yet.

    Prefers the document's own ``page_content`` (where a cloud whole-page pass
    normally lands); falls back to the newest ``transcription`` artifact's
    content. Returns ``None`` — never an empty string — when there is nothing to
    align, so the caller can say "no transcript" rather than align against "".
    """
    document = db.get(Document, document_id)  # type: ignore[attr-defined]
    if document is not None and (document.page_content or "").strip():
        return document.page_content

    transcriptions = db.query(  # type: ignore[attr-defined]
        Artifact, document_id=document_id, artifact_type="transcription"
    )
    newest = max(
        (a for a in transcriptions if (a.content or "").strip()),
        key=lambda a: a.created_at,
        default=None,
    )
    return newest.content if newest is not None else None


def align_and_build_artifact(
    regions_artifact: Artifact,
    transcript: str,
) -> tuple[OCRGeometryResult, Artifact | None]:
    """Align ``transcript`` to ``regions_artifact``'s baselines.

    Returns ``(aligned_geometry, artifact)``. ``aligned_geometry.metadata`` always
    carries the :class:`AlignmentStatus` (read it to explain a decline). The
    ``artifact`` is built ONLY when alignment succeeded — a declined attempt
    persists nothing, so a mismatch never leaves a wrong overlay behind. The
    caller is responsible for ``db.save``-ing a returned artifact.
    """
    regions = regions_artifact.ocr_geometry or OCRGeometryResult(
        provider=regions_artifact.provider or "kraken",
        model=regions_artifact.model,
    )
    aligned = align_transcript_to_baselines(transcript, regions)

    if aligned.metadata.get(STATUS_KEY) != AlignmentStatus.ALIGNED.value:
        return aligned, None

    artifact = Artifact(
        document_id=regions_artifact.document_id,
        artifact_type=ALIGNED_ARTIFACT_TYPE,
        content=transcript,
        ocr_geometry=aligned,
        provider=regions_artifact.provider or "kraken",
        model=regions_artifact.model,
        source_artifact_id=regions_artifact.id,
        confidence=aligned.metadata.get(CONFIDENCE_KEY),
        data={
            GROUND_TRUTH_KEY: aligned.metadata.get(GROUND_TRUTH_KEY),
            CONFIDENCE_KEY: aligned.metadata.get(CONFIDENCE_KEY),
            TRANSCRIPT_LINE_COUNT_KEY: aligned.metadata.get(TRANSCRIPT_LINE_COUNT_KEY),
            BASELINE_COUNT_KEY: aligned.metadata.get(BASELINE_COUNT_KEY),
            UNMATCHED_LINES_KEY: aligned.metadata.get(UNMATCHED_LINES_KEY),
            "source_regions_artifact_id": regions_artifact.id,
        },
    )
    return aligned, artifact
