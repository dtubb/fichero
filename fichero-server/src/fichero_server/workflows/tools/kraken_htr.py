"""Kraken per-line HTR: recognise each line and tie its text to its baseline.

The economy_htr ``kraken`` backend runs the kraken CLI full-page and returns
only joined text — no per-line geometry — so recognised text cannot be anchored
to the baselines the blla segmenter finds. This node uses the engine's
``recognize_to_geometry`` (segment + rpred, in the Kraken venv) so every line
comes back with the text Kraken read AND the baseline it read it from, then
SAVES it: ``result.text`` becomes the page's ``page_content`` and the per-line
baseline/polygon geometry is stored on a ``transcription`` artifact's
``ocr_geometry`` — the same shape the reader overlays and the HTR training plan
consumes. Pure on-device Kraken, no LLM (Daniel: "i want kraken text saved, and
ideally tied to the baselines").
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.tools.llm_base import save_artifact
from fichero_server.workflows.tools.vision_base import VisionToolConfig

logger = logging.getLogger(__name__)


TOOL_CONFIG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=True,
    trigger_embedding=True,
    # Kraken is not Apple Vision; its own segmenter+recogniser is the engine.
    supports_apple_vision=False,
    metadata_field="transcription",
    # Kraken RECOGNISES the page — it does not hand back a stored transcription;
    # never short-circuit to already-extracted text.
    accepts_extracted_text=False,
)

KRAKEN_HTR_CONFIG = {
    "kraken_model": {
        "type": "string",
        "default": "kraken-mccatmus",
        "description": (
            "Catalog id of the Kraken recognition model (e.g. 'kraken-mccatmus', "
            "'kraken-catmus-medieval'), or a literal path to a .mlmodel. Install "
            "it from Settings -> AI -> Local Inference first."
        ),
    },
    "update_page_content": {
        "type": "boolean",
        "default": True,
        "description": "Promote the recognised transcript to page_content (index for search).",
    },
    "save_to_db": {
        "type": "boolean",
        "default": True,
        "description": "Persist the transcription + per-line baseline geometry.",
    },
}


def _resolve_model_path(model_ref: str) -> tuple[str, str | None]:
    """(filesystem path, catalog id) for a recognition model reference.

    A catalog id ("kraken-mccatmus") resolves to the app's downloaded copy; a
    literal ``.mlmodel`` path is used as-is. Raises a clear, actionable error
    when a catalog model is not installed — never runs against a missing path.
    """
    from fichero_server.llm import kraken_runtime

    if model_ref in kraken_runtime.KRAKEN_RECOGNITION_MODELS:
        resolved = kraken_runtime.recognition_model_path(model_ref)
        if not resolved:
            raise RuntimeError(
                f"Kraken recognition model '{model_ref}' is not downloaded — "
                "install it from Settings -> AI -> Local Inference (the on-device "
                "model catalog)."
            )
        return resolved, model_ref
    if not model_ref:
        raise RuntimeError(
            "Kraken HTR needs a recognition model — set 'kraken_model' to a catalog "
            "id (e.g. 'kraken-mccatmus') or a path to a .mlmodel."
        )
    if not Path(model_ref).exists():
        raise RuntimeError(f"Kraken recognition model not found: {model_ref}")
    return model_ref, None


@register_tool(
    name="kraken_htr",
    display_name="Kraken HTR (per-line)",
    description=(
        "On-device Kraken handwriting recognition: neural baseline segmentation "
        "+ a recognition model reads each line, saving the transcript tied to its "
        "baselines (no LLM)."
    ),
    category="vision",
    icon="text.viewfinder",
    color="mint",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False),
    ],
    output_ports=[
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT),
        PortDef(id="records", name="Records", port_type="output", data_type=DataType.JSON),
        PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        PortDef(id="documents", name="Documents", port_type="output", data_type=DataType.JSON),
    ],
    config_schema=KRAKEN_HTR_CONFIG,
    sort_order=29,
)
async def kraken_htr(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Recognise each page's lines with Kraken and save text tied to baselines."""
    from fichero_server.llm.kraken_runtime import recognize_to_geometry

    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]
    documents = list(inputs.get("documents") or []) or documents_from_state_outputs(state, files)

    model_ref = inputs.get("kraken_model", "kraken-mccatmus")
    model_path, model_id = _resolve_model_path(model_ref)
    # Stamp the box provenance with the catalog id when we have one, else the path.
    stamped = model_id or model_path
    kraken_config = LLMConfig(provider="kraken", model=stamped)

    library_path = state.get("library_path", "")
    save = bool(inputs.get("save_to_db", True)) and bool(library_path)

    records: list[dict[str, Any]] = []
    texts: list[str] = []
    errors: list[str] = []
    for index, file_path in enumerate(files):
        document = documents[index] if index < len(documents) else None
        doc_id = document.get("id") if isinstance(document, dict) else None
        if str(file_path).lower().endswith(".pdf"):
            # Kraken reads page IMAGES; a PDF must be split first (same rule as
            # the segmenter seam). Report per-file rather than aborting the run.
            errors.append(f"{Path(file_path).name}: split the PDF into page images first")
            continue
        try:
            result = await asyncio.to_thread(
                recognize_to_geometry, file_path, model_path, model_id=model_id
            )
        except Exception as exc:  # noqa: BLE001 — isolate one bad page from the rest
            logger.warning("kraken_htr failed on %s: %s", file_path, exc)
            errors.append(f"{Path(file_path).name}: {exc}")
            continue

        texts.append(result.text)
        if doc_id:
            records.append({"doc_id": doc_id, "text": result.text})
        if save and (doc_id or (isinstance(document, dict) and document.get("path"))):
            # save_artifact stores the transcription WITH its ocr_geometry (the
            # per-line baselines) and promotes result.text to page_content.
            await save_artifact(
                document_id=doc_id,
                file_path=document.get("path") if isinstance(document, dict) else file_path,
                content=result.text,
                data=None,
                library_path=library_path,
                llm_config=kraken_config,
                task_id=state.get("task_id"),
                tool_config=TOOL_CONFIG,
                ocr_geometry=result,
                document=document if isinstance(document, dict) else None,
            )

    return {
        "text": "\n\n".join(t for t in texts if t),
        "texts": texts,
        "records": records,
        "files": list(files),
        "documents": documents,
        "output_files": list(files),
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
