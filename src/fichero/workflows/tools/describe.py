"""
Describe Tool

Generates descriptions of images using vision LLM.
Saves results to Artifact and updates Document metadata.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Building (defined first so decorator can use it)
# =============================================================================

def _build_describe_prompt(detail_level: str, focus: str) -> str:
    """Build the description prompt."""
    detail_instructions = {
        "brief": "Provide a brief, one-sentence description.",
        "detailed": "Provide a detailed description covering main elements, composition, and context.",
        "comprehensive": "Provide a comprehensive description including all visible elements, their relationships, colors, textures, lighting, and any text or symbols.",
    }

    prompt = f"""Describe this image.

{detail_instructions.get(detail_level, detail_instructions["detailed"])}
"""

    if focus:
        prompt += f"\nFocus particularly on: {focus}"

    return prompt


def build_describe_prompt(config: dict) -> str:
    """Build the description prompt from config.

    This is exposed to the UI so users can see and edit the prompt.
    """
    detail_level = config.get("detail_level", "detailed")
    focus = config.get("focus", "")
    return _build_describe_prompt(detail_level, focus)


# =============================================================================
# Tool Registration
# =============================================================================

@register_tool(
    name="describe",
    display_name="Describe",
    description="Generate descriptions of images using vision LLM. Saves to database.",
    category="vision",
    icon="eye",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True, description="Image files to describe"),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False, description="Document metadata for saving results"),
    ],
    output_ports=[
        PortDef(id="description", name="Description", port_type="output", data_type=DataType.TEXT, description="Combined description"),
        PortDef(id="descriptions", name="Descriptions", port_type="output", data_type=DataType.ARRAY, description="Array of individual descriptions"),
        PortDef(id="structured", name="Structured", port_type="output", data_type=DataType.JSON, description="Full results with file info"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "detail_level": {"type": "string", "enum": ["brief", "detailed", "comprehensive"], "default": "detailed", "description": "Level of detail in description"},
        "focus": {"type": "string", "description": "What to focus on (e.g., 'people', 'objects', 'text', 'scene')"},
        "prompt": {"type": "string", "description": "Custom prompt (overrides default)"},
        "save_to_db": {"type": "boolean", "default": True, "description": "Save description to document in database"},
    },
    default_output_schema={
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Image description"},
            "subjects": {"type": "array", "items": {"type": "string"}, "description": "Main subjects in image"},
            "setting": {"type": "string", "description": "Setting or context"},
        }
    },
    # Default prompt shown in UI (with default config)
    default_prompt=_build_describe_prompt("detailed", ""),
    # Dynamic prompt builder based on config
    prompt_builder=build_describe_prompt,
    sort_order=11,
)
async def describe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate descriptions of images using vision LLM.

    Args:
        inputs: Resolved inputs from workflow
        state: Current workflow state
        llm_config: LLM configuration

    Returns:
        Dict with descriptions and artifact IDs
    """
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    detail_level = inputs.get("detail_level", "detailed")
    focus = inputs.get("focus", "")
    prompt_override = inputs.get("prompt")
    save_to_db = inputs.get("save_to_db", True)

    library_path = state.get("library_path", "")

    if isinstance(files, str):
        files = [files]

    if not files:
        return {"description": "", "descriptions": [], "artifacts": [], "error": "No input files provided"}

    # Build path -> document_id mapping
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                path_to_doc[doc["path"]] = doc.get("id")

    # Build prompt
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = _build_describe_prompt(detail_level, focus)

    results = []
    descriptions = []
    artifact_ids = []

    for file_path in files:
        try:
            image_uri = _file_to_data_uri(file_path)

            description = await vision(
                images=[image_uri],
                prompt=prompt,
                config=llm_config,
            )

            result = {
                "file": file_path,
                "description": description,
            }

            if save_to_db and library_path:
                artifact_id = await _save_description(
                    file_path=file_path,
                    description=description,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=llm_config,
                    task_id=state.get("task_id"),
                )
                if artifact_id:
                    result["artifact_id"] = artifact_id
                    artifact_ids.append(artifact_id)

            results.append(result)
            descriptions.append(description)

        except Exception as e:
            logger.error(f"Failed to describe {file_path}: {e}")
            results.append({
                "file": file_path,
                "description": "",
                "error": str(e),
            })
            descriptions.append("")

    return {
        "description": "\n\n".join(descriptions),
        "descriptions": descriptions,
        "results": results,
        "artifacts": artifact_ids,
    }


async def _save_description(
    file_path: str,
    description: str,
    document_id: str | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
) -> str | None:
    """Save description to database as Artifact."""
    try:
        from fichero.db import db_manager
        from fichero.models import Document, Artifact

        db = db_manager.get_database(library_path)

        doc = None
        if document_id:
            doc = db.get(Document, document_id)
        if not doc:
            docs = db.query(Document, path=file_path)
            if docs:
                doc = docs[0]

        if not doc:
            logger.warning(f"Document not found for path: {file_path}")
            return None

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="description",
            content=description,
            provider=llm_config.provider,
            model=llm_config.model,
            run_id=task_id,
        )
        db.save(artifact)
        logger.info(f"Created description artifact {artifact.id} for document {doc.id}")

        # Update document metadata with description
        if "description" not in doc.metadata:
            doc.metadata["description"] = description
            doc.updated_at = datetime.now()
            db.save(doc)

        return artifact.id

    except Exception as e:
        logger.error(f"Failed to save description for {file_path}: {e}")
        return None


def _file_to_data_uri(file_path: str) -> str:
    """Convert a file to a base64 data URI."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"
