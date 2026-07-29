"""Annotations-as-input source tool (#914 follow-up).

Emits one (file_path, document, crop_content) tuple per Annotation
on a selected document so downstream LLM/vision tools operate only
on the highlighted region. Supports the use case:
"highlight 10% of a 100MB image and the AI sees that."

Wiring:
    [Annotations source] → fan_out (one branch per annotation)
                       ↘ [Transcribe / Catalogue / ...]

Each branch gets:
- ``files`` — the cropped PNG (image / PDF region) or a temp-file
  with the cropped text.
- ``documents`` — the original document plus annotation metadata
  so the downstream tool's results stay anchored to the right
  annotation_id.
- ``annotation_id`` — the row's id, so when a Catalogue claim
  gets created the inspector can show "from highlight 〈excerpt〉"
  via the linked_claim_ids back-link.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef

logger = logging.getLogger(__name__)


@register_tool(
    name="annotations_source",
    display_name="Annotations Source",
    description=(
        "Iterate a document's user highlights / notes / regions and "
        "emit one cropped input per annotation. Use upstream of any "
        "vision or LLM tool to make the AI operate on a marked "
        "region instead of the whole document. (#914)"
    ),
    category="source",
    icon="highlighter",
    color="yellow",
    uses_llm=False,
    supports_batch=False,
    input_ports=[],
    output_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="output",
            data_type=DataType.FILES,
            description=(
                "One cropped file per annotation (PNG for image / "
                "PDF regions, .txt for text highlights). The crops "
                "live in a tmp dir and survive for the workflow run."
            ),
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description=(
                "One document entry per crop: the original document "
                "metadata + annotation_id + crop_kind so downstream "
                "tools can link results back to the right annotation."
            ),
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of annotation crops emitted.",
        ),
    ],
    config_schema={
        "kinds": {
            "type": "array",
            "default": ["highlight", "bookmark"],
            "description": (
                "Annotation kinds to iterate. Defaults to highlight "
                "+ bookmark (the spatial / span-anchored kinds); "
                "exclude 'rating' which carries no crop content."
            ),
            "items": {
                "type": "string",
                "enum": ["highlight", "note", "rating", "bookmark", "comment"],
            },
        },
        "min_rating": {
            "type": "number",
            "default": 0,
            "description": (
                "Only emit annotations with rating >= this value. 0 "
                "(default) means include all. Use to focus the AI on "
                "the user's most-important highlights."
            ),
        },
    },
    sort_order=5,
)
async def annotations_source_tool(
    inputs: dict[str, Any],
    state: dict[str, Any],
    llm_config: Any,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit one (file, document, count) entry per matching annotation."""
    from fichero_server.db import db_manager
    from fichero_server.models.knowledge import Annotation
    from fichero_server.models import Document
    from fichero_server.workflows.tools._annotation_input import (
        crop_image,
        crop_pdf_page,
        crop_text,
    )

    library_path = state.get("library_path")
    if not library_path:
        logger.warning("annotations_source: no library_path in state")
        return {"files": [], "documents": [], "count": 0}
    db = db_manager.get_database(library_path)

    config = config or {}
    kinds_filter = set(config.get("kinds") or ["highlight", "bookmark"])
    min_rating = float(config.get("min_rating") or 0)

    selected_doc_ids = state.get("selected_doc_ids") or []
    if not selected_doc_ids:
        return {"files": [], "documents": [], "count": 0}

    # Gather all matching annotations across the selected documents.
    matching: list[tuple[Document, Annotation]] = []
    for doc_id in selected_doc_ids:
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        for ann in db.query(Annotation, document_id=doc_id):
            kind_value = ann.kind.value if hasattr(ann.kind, "value") else str(ann.kind)
            if kind_value not in kinds_filter:
                continue
            if min_rating and (ann.rating or 0) < min_rating:
                continue
            matching.append((doc, ann))

    if not matching:
        return {"files": [], "documents": [], "count": 0}

    # Crop each annotation into a tempfile downstream tools can read.
    tmp_dir = Path(tempfile.mkdtemp(prefix="fichero-annotations-"))
    files: list[str] = []
    documents: list[dict[str, Any]] = []

    for idx, (doc, ann) in enumerate(matching):
        suffix = Path(doc.path).suffix.lower() if doc.path else ""

        # Pick the right cropper based on doc type + whether bbox is set.
        crop_bytes: bytes | None = None
        crop_text_val: str | None = None
        crop_kind = "unknown"
        if doc.path and ann.bbox and suffix == ".pdf":
            crop_bytes = crop_pdf_page(doc.path, ann)
            crop_kind = "pdf_region_png"
        elif doc.path and ann.bbox and suffix in {
            ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic",
        }:
            crop_bytes = crop_image(doc.path, ann)
            crop_kind = "image_region_png"
        else:
            crop_text_val = crop_text(doc, ann)
            crop_kind = "text"

        # Write the crop to disk so file-path-oriented tools (Transcribe,
        # Catalogue) can consume it. PNG bytes → .png file; text → .txt.
        out_name = f"ann-{idx:04d}-{ann.id}"
        if crop_bytes is not None:
            out_path = tmp_dir / f"{out_name}.png"
            out_path.write_bytes(crop_bytes)
        elif crop_text_val is not None:
            out_path = tmp_dir / f"{out_name}.txt"
            out_path.write_text(crop_text_val, encoding="utf-8")
        else:
            continue  # skip annotations with no crop

        files.append(str(out_path))
        # Pass through the original document metadata + annotation
        # context so downstream tools can attribute results.
        doc_meta = doc.model_dump(mode="json")
        doc_meta["annotation_id"] = ann.id
        doc_meta["annotation_kind"] = (
            ann.kind.value if hasattr(ann.kind, "value") else str(ann.kind)
        )
        doc_meta["crop_kind"] = crop_kind
        doc_meta["crop_path"] = str(out_path)
        if ann.text:
            doc_meta["annotation_text"] = ann.text
        documents.append(doc_meta)

    logger.info(
        "annotations_source: emitted %d crops from %d annotations across "
        "%d documents → tmp=%s",
        len(files), len(matching), len(selected_doc_ids), tmp_dir,
    )
    return {"files": files, "documents": documents, "count": len(files)}
