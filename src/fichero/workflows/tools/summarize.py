"""
Summarize Tools

Generate summaries at different levels:
- summarize_file: Summarize a single document
- summarize_folder: Summarize all documents in a folder
- summarize_collection: Summarize an entire collection

All save results to Artifacts linked to the appropriate Document.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.llm import chat, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Summarize File (single document)
# =============================================================================

@register_tool(
    name="summarize_file",
    display_name="Summarize File",
    description="Generate a summary of a single document's content",
    category="llm",
    icon="doc.text",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT, required=True, description="Text content to summarize"),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False, description="Document metadata for saving"),
    ],
    output_ports=[
        PortDef(id="summary", name="Summary", port_type="output", data_type=DataType.TEXT, description="Generated summary"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "style": {"type": "string", "enum": ["brief", "detailed", "bullets"], "default": "brief", "description": "Summary style"},
        "max_length": {"type": "integer", "default": 200, "description": "Max words in summary"},
        "prompt": {"type": "string", "description": "Custom prompt override"},
        "save_to_db": {"type": "boolean", "default": True, "description": "Save summary to database"},
    },
    default_output_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
        }
    },
    sort_order=30,
)
async def summarize_file(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize a single document."""
    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    style = inputs.get("style", "brief")
    max_length = inputs.get("max_length", 200)
    prompt_override = inputs.get("prompt")
    save_to_db = inputs.get("save_to_db", True)

    library_path = state.get("library_path", "")

    if not text:
        return {"summary": "", "artifacts": [], "error": "No text provided"}

    # Build prompt
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = _build_summary_prompt(text, style, max_length)

    try:
        summary = await chat(
            messages=[{"role": "user", "content": prompt}],
            config=llm_config,
        )

        artifact_ids = []

        # Save to database if we have document info
        if save_to_db and library_path and documents:
            for doc in documents[:1]:  # Save to first document
                if isinstance(doc, dict) and doc.get("id"):
                    artifact_id = await _save_summary(
                        document_id=doc["id"],
                        summary=summary,
                        summary_type="file",
                        library_path=library_path,
                        llm_config=llm_config,
                        task_id=state.get("task_id"),
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)

        return {
            "summary": summary,
            "artifacts": artifact_ids,
        }

    except Exception as e:
        logger.error(f"Failed to summarize: {e}")
        return {"summary": "", "artifacts": [], "error": str(e)}


# =============================================================================
# Summarize Folder
# =============================================================================

@register_tool(
    name="summarize_folder",
    display_name="Summarize Folder",
    description="Generate a summary of all documents in a folder",
    category="llm",
    icon="folder",
    color="purple",
    uses_llm=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="texts", name="Texts", port_type="input", data_type=DataType.ARRAY, required=True, description="Array of text contents"),
        PortDef(id="folder_id", name="Folder ID", port_type="input", data_type=DataType.TEXT, required=False, description="Folder document ID"),
    ],
    output_ports=[
        PortDef(id="summary", name="Summary", port_type="output", data_type=DataType.TEXT, description="Folder summary"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "style": {"type": "string", "enum": ["brief", "detailed", "bullets"], "default": "detailed"},
        "max_length": {"type": "integer", "default": 500},
        "include_themes": {"type": "boolean", "default": True, "description": "Include common themes"},
        "save_to_db": {"type": "boolean", "default": True},
    },
    sort_order=31,
)
async def summarize_folder(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize all documents in a folder."""
    texts = inputs.get("texts", [])
    folder_id = inputs.get("folder_id", "")
    style = inputs.get("style", "detailed")
    max_length = inputs.get("max_length", 500)
    include_themes = inputs.get("include_themes", True)
    save_to_db = inputs.get("save_to_db", True)

    library_path = state.get("library_path", "")

    if not texts:
        return {"summary": "", "artifacts": [], "error": "No texts provided"}

    # Combine texts with separators
    combined = "\n\n---\n\n".join([t for t in texts if t])

    prompt = f"""Summarize the following collection of {len(texts)} documents.

{_get_style_instructions(style, max_length)}

{"Identify common themes, patterns, or connections between documents." if include_themes else ""}

Documents:
{combined}
"""

    try:
        summary = await chat(
            messages=[{"role": "user", "content": prompt}],
            config=llm_config,
        )

        artifact_ids = []

        if save_to_db and library_path and folder_id:
            artifact_id = await _save_summary(
                document_id=folder_id,
                summary=summary,
                summary_type="folder",
                library_path=library_path,
                llm_config=llm_config,
                task_id=state.get("task_id"),
            )
            if artifact_id:
                artifact_ids.append(artifact_id)

        return {
            "summary": summary,
            "artifacts": artifact_ids,
            "document_count": len(texts),
        }

    except Exception as e:
        logger.error(f"Failed to summarize folder: {e}")
        return {"summary": "", "artifacts": [], "error": str(e)}


# =============================================================================
# Summarize Collection
# =============================================================================

@register_tool(
    name="summarize_collection",
    display_name="Summarize Collection",
    description="Generate a high-level summary of an entire collection",
    category="llm",
    icon="archivebox",
    color="purple",
    uses_llm=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="folder_summaries", name="Folder Summaries", port_type="input", data_type=DataType.ARRAY, required=False, description="Summaries from folders"),
        PortDef(id="texts", name="Texts", port_type="input", data_type=DataType.ARRAY, required=False, description="Or raw texts if no folder summaries"),
        PortDef(id="collection_id", name="Collection ID", port_type="input", data_type=DataType.TEXT, required=False, description="Collection document ID"),
    ],
    output_ports=[
        PortDef(id="summary", name="Summary", port_type="output", data_type=DataType.TEXT, description="Collection summary"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "style": {"type": "string", "enum": ["executive", "detailed", "narrative"], "default": "executive"},
        "max_length": {"type": "integer", "default": 1000},
        "include_statistics": {"type": "boolean", "default": True},
        "save_to_db": {"type": "boolean", "default": True},
    },
    sort_order=32,
)
async def summarize_collection(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize an entire collection."""
    folder_summaries = inputs.get("folder_summaries", [])
    texts = inputs.get("texts", [])
    collection_id = inputs.get("collection_id", "")
    style = inputs.get("style", "executive")
    max_length = inputs.get("max_length", 1000)
    include_statistics = inputs.get("include_statistics", True)
    save_to_db = inputs.get("save_to_db", True)

    library_path = state.get("library_path", "")

    # Use folder summaries if available, otherwise raw texts
    content_items = folder_summaries if folder_summaries else texts

    if not content_items:
        return {"summary": "", "artifacts": [], "error": "No content provided"}

    combined = "\n\n---\n\n".join([str(t) for t in content_items if t])

    style_instructions = {
        "executive": "Provide an executive summary suitable for quick review. Focus on key findings and overall themes.",
        "detailed": "Provide a comprehensive summary covering all major topics and their relationships.",
        "narrative": "Provide a narrative summary that tells the story of this collection.",
    }

    prompt = f"""Summarize this collection of documents.

{style_instructions.get(style, style_instructions["executive"])}

Maximum length: {max_length} words.

{"Include statistics about the collection (e.g., number of documents, date ranges, main topics)." if include_statistics else ""}

Content:
{combined}
"""

    try:
        summary = await chat(
            messages=[{"role": "user", "content": prompt}],
            config=llm_config,
        )

        artifact_ids = []

        if save_to_db and library_path and collection_id:
            artifact_id = await _save_summary(
                document_id=collection_id,
                summary=summary,
                summary_type="collection",
                library_path=library_path,
                llm_config=llm_config,
                task_id=state.get("task_id"),
            )
            if artifact_id:
                artifact_ids.append(artifact_id)

        return {
            "summary": summary,
            "artifacts": artifact_ids,
            "source_count": len(content_items),
        }

    except Exception as e:
        logger.error(f"Failed to summarize collection: {e}")
        return {"summary": "", "artifacts": [], "error": str(e)}


# =============================================================================
# Helper Functions
# =============================================================================

async def _save_summary(
    document_id: str,
    summary: str,
    summary_type: str,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
) -> str | None:
    """Save summary to database as Artifact."""
    try:
        from fichero.db import db_manager
        from fichero.models import Document, Artifact

        db = db_manager.get_database(library_path)

        doc = db.get(Document, document_id)
        if not doc:
            logger.warning(f"Document not found: {document_id}")
            return None

        artifact = Artifact(
            document_id=doc.id,
            artifact_type=f"summary_{summary_type}",
            content=summary,
            provider=llm_config.provider,
            model=llm_config.model,
            run_id=task_id,
        )
        db.save(artifact)
        logger.info(f"Created {summary_type} summary artifact {artifact.id} for document {doc.id}")

        # Update document metadata
        doc.metadata[f"summary_{summary_type}"] = summary[:500]  # Store truncated version in metadata
        doc.updated_at = datetime.now()
        db.save(doc)

        return artifact.id

    except Exception as e:
        logger.error(f"Failed to save summary: {e}")
        return None


def _build_summary_prompt(text: str, style: str, max_length: int) -> str:
    """Build the summary prompt for a single document."""
    return f"""Summarize the following text.

{_get_style_instructions(style, max_length)}

Text:
{text}
"""


def _get_style_instructions(style: str, max_length: int) -> str:
    """Get style-specific instructions."""
    instructions = {
        "brief": f"Provide a brief summary in 1-2 sentences (max {max_length} words).",
        "detailed": f"Provide a detailed summary covering main points (max {max_length} words).",
        "bullets": f"Provide a bullet-point summary with key takeaways (max {max_length} words).",
    }
    return instructions.get(style, instructions["brief"])
