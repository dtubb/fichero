"""Merge Geometry — tie a reviewed transcription to the best word boxes we have.

Daniel: "is there no way to merge the word regions so that a transcription
review can have its words tied to the best word region we have?"

Two artifacts describe the same page and disagree. `regions` carries measured
word boxes labelled with what the OCR thought it read; `transcription_review`
carries the correct text and no geometry. This step marries them, so clicking
a word in the corrected transcript highlights it on the image.

The alignment lives in `media.geometry_merge`, with no database or workflow in
it, so it is tested on strings and rectangles alone. This tool is the part that
knows which artifacts to feed it and where to put the answer.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef

logger = logging.getLogger(__name__)

MERGED_ARTIFACT_TYPE = "text_geometry"


@register_tool(
    name="merge_geometry",
    display_name="Merge Geometry",
    description=(
        "Place a reviewed transcription's words on the measured word boxes "
        "from an OCR pass, so corrected text becomes clickable on the page. "
        "Every word records whether its box was measured or interpolated, and "
        "a page whose line structure cannot be trusted is refused rather than "
        "given a confident wrong overlay."
    ),
    category="text",
    icon="text.viewfinder",
    color="teal",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            description="Documents whose artifacts should be merged.",
        ),
    ],
    output_ports=[
        PortDef(
            id="records", name="Records", port_type="output",
            data_type=DataType.ARRAY,
            description="One {doc_id, merged, reason} per document.",
        ),
        PortDef(
            id="artifacts", name="Artifacts", port_type="output",
            data_type=DataType.ARRAY,
            description="Ids of the geometry artifacts written.",
        ),
        PortDef(
            id="count", name="Count", port_type="output", data_type=DataType.NUMBER,
        ),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "text_artifact_type": {
                "type": "string",
                "default": "transcription_review",
                "description": "Which artifact holds the CORRECT text",
            },
            "geometry_artifact_type": {
                "type": "string",
                "default": "regions",
                "description": "Which artifact holds the MEASURED boxes",
            },
            "step_name": {
                "type": "string",
                "description": "Restrict the text artifact to one step (r1, r2, r3)",
            },
        },
    },
    sort_order=48,
)
async def merge_geometry_tool(
    inputs: dict[str, Any],
    state: dict[str, Any],
    llm_config: Any,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge each selected document's reviewed text onto its measured boxes."""
    from fichero_server.db import db_manager
    from fichero_server.media.geometry_merge import merge_reviewed_text_onto_geometry
    from fichero_server.media.ocr_geometry import OCRGeometryResult
    from fichero_server.models import Artifact

    empty: dict[str, Any] = {"records": [], "artifacts": [], "count": 0}

    library_path = state.get("library_path")
    if not library_path:
        logger.warning("merge_geometry: no library_path in state")
        return empty

    documents = inputs.get("documents") or []
    doc_ids = [
        d.get("id") for d in documents if isinstance(d, dict) and d.get("id")
    ] or list(state.get("selected_doc_ids") or [])
    if not doc_ids:
        logger.warning("merge_geometry: nothing selected")
        return empty

    config = {**(config or {}), **{k: v for k, v in inputs.items() if k in (
        "text_artifact_type", "geometry_artifact_type", "step_name"
    )}}
    text_type = str(config.get("text_artifact_type") or "transcription_review")
    geometry_type = str(config.get("geometry_artifact_type") or "regions")
    step_name = str(config.get("step_name") or "").strip()

    db = db_manager.get_database(library_path)
    records: list[dict[str, Any]] = []
    artifact_ids: list[str] = []

    for doc_id in doc_ids:
        text_rows = db.query(Artifact, document_id=doc_id, artifact_type=text_type)
        if step_name:
            text_rows = [r for r in text_rows if (r.step_name or "") == step_name]
        geometry_rows = db.query(
            Artifact, document_id=doc_id, artifact_type=geometry_type
        )
        # A document missing either half is reported, not skipped in silence:
        # a chain that merged four of five pages must not look complete.
        if not text_rows or not geometry_rows:
            missing = "reviewed text" if not text_rows else "measured geometry"
            logger.info("merge_geometry: %s has no %s", doc_id, missing)
            records.append({"doc_id": doc_id, "merged": False,
                            "reason": f"no {missing} artifact"})
            continue

        for rows in (text_rows, geometry_rows):
            rows.sort(key=lambda r: (r.created_at is not None, r.created_at))
        reviewed_text = (text_rows[-1].content or "").strip()
        raw_geometry = geometry_rows[-1].ocr_geometry
        if not reviewed_text or not raw_geometry:
            records.append({"doc_id": doc_id, "merged": False,
                            "reason": "artifact present but empty"})
            continue

        try:
            measured = (
                raw_geometry
                if isinstance(raw_geometry, OCRGeometryResult)
                else OCRGeometryResult.model_validate(raw_geometry)
            )
        except Exception as exc:  # noqa: BLE001 — a bad row must not end the run
            logger.warning("merge_geometry: %s geometry unreadable: %s", doc_id, exc)
            records.append({"doc_id": doc_id, "merged": False,
                            "reason": f"geometry unreadable: {exc}"})
            continue

        outcome = merge_reviewed_text_onto_geometry(reviewed_text, measured)
        if outcome.refused or outcome.result is None:
            logger.info("merge_geometry: %s refused — %s", doc_id, outcome.reason)
            records.append({"doc_id": doc_id, "merged": False,
                            "reason": outcome.reason})
            continue

        artifact = Artifact(
            document_id=doc_id,
            artifact_type=MERGED_ARTIFACT_TYPE,
            content=reviewed_text,
            ocr_geometry=outcome.result,
            # NOT the OCR provider: `aligned:<engine>` says a person's (or a
            # stronger model's) text was placed on that engine's boxes, part
            # measured and part interpolated. A backfilled page that reported
            # itself as `apple_vision` would be indistinguishable from a
            # measured one for every consumer that ranks or trusts geometry.
            provider=outcome.result.provider,
            model=measured.model,
            source_artifact_id=text_rows[-1].id,
            source_document_id=doc_id,
            run_id=state.get("task_id"),
            step_name="merge_geometry",
        )
        db.save(artifact)
        artifact_ids.append(artifact.id)
        records.append({
            "doc_id": doc_id,
            "merged": True,
            "artifact_id": artifact.id,
            "lines_matched": outcome.lines_matched,
            "lines_total": outcome.lines_total,
            "measured_words": outcome.measured_words,
            "derived_words": outcome.derived_words,
        })

    return {
        "records": records,
        "artifacts": artifact_ids,
        "count": len(artifact_ids),
    }
