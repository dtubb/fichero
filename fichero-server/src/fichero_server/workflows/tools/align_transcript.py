"""Align Transcript — hang a page's known transcript on its Kraken baselines.

Kraken's Detect Regions pass leaves one polygon + baseline per line but reads
nothing. When the page already has a good transcript (usually a cloud
whole-page pass), this node joins the two by pure line-level forced alignment —
no model, no network — and writes an ``aligned_transcript`` artifact whose
geometry the reader overlay draws directly.

Honest by default (see :mod:`media.transcript_alignment`): a page is aligned
only when its transcript line count matches its baseline count; a mismatch
writes NOTHING for that page and is logged, so a wrong line never lands on a
baseline. Runs on the selected documents, like ``artifacts_source``.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import DataType, PortDef
from fichero_server.workflows.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="align_transcript",
    display_name="Align Transcript to Baselines",
    description=(
        "Joins a page's known transcript to its Kraken line baselines, on-device "
        "and free — no model runs. Each transcript line is hung on its baseline "
        "in reading order, so the reader can anchor the text to the page image. "
        "A page whose line count does not match its baseline count is left "
        "unaligned rather than have the wrong text placed on it. Run after "
        "Detect Regions (Kraken) on pages that already have a transcript."
    ),
    category="vision",
    icon="text.line.first.and.arrowtriangle.forward",
    color="purple",
    uses_llm=False,
    supports_batch=False,
    input_ports=[],
    output_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="The documents processed, so a downstream step links back.",
        ),
        PortDef(
            id="aligned_count",
            name="Aligned",
            port_type="output",
            data_type=DataType.NUMBER,
            description="How many pages were aligned (exact line-count match).",
        ),
        PortDef(
            id="skipped_count",
            name="Skipped",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Pages left unaligned (no transcript, no baselines, or mismatch).",
        ),
    ],
    config_schema={},
    sort_order=5,
)
async def align_transcript_tool(
    inputs: dict[str, Any],
    state: dict[str, Any],
    llm_config: Any,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Forced-align the selected pages' transcripts to their Kraken baselines."""
    from fichero_server.db import db_manager
    from fichero_server.media.transcript_alignment_service import (
        align_and_build_artifact,
        resolve_transcript,
    )
    from fichero_server.models import Artifact

    empty: dict[str, Any] = {"documents": [], "aligned_count": 0, "skipped_count": 0}

    library_path = state.get("library_path")
    if not library_path:
        logger.warning("align_transcript: no library_path in state")
        return empty
    selected_doc_ids = state.get("selected_doc_ids") or []
    if not selected_doc_ids:
        logger.warning("align_transcript: nothing selected")
        return empty

    db = db_manager.get_database(library_path)
    documents: list[dict[str, Any]] = []
    aligned_count = 0
    skipped_count = 0

    for doc_id in selected_doc_ids:
        regions = db.query(Artifact, document_id=doc_id, artifact_type="regions")
        # Newest regions artifact that actually carries baselines. A page can
        # accumulate empty/older ones; the freshest with geometry is the one to
        # align to.
        regions = [r for r in regions if r.ocr_geometry and r.ocr_geometry.boxes]
        if not regions:
            logger.info("align_transcript: %s has no baseline regions", doc_id)
            skipped_count += 1
            continue
        regions.sort(key=lambda r: (r.created_at is not None, r.created_at))
        regions_artifact = regions[-1]

        transcript = resolve_transcript(db, doc_id)
        if not transcript:
            logger.info("align_transcript: %s has no transcript to align", doc_id)
            skipped_count += 1
            continue

        _aligned, artifact = align_and_build_artifact(regions_artifact, transcript)
        if artifact is None:
            logger.info("align_transcript: %s declined (line/baseline mismatch)", doc_id)
            skipped_count += 1
            continue

        db.save(artifact)
        aligned_count += 1
        documents.append({"doc_id": doc_id, "artifact_id": artifact.id})

    return {
        "documents": documents,
        "aligned_count": aligned_count,
        "skipped_count": skipped_count,
    }
