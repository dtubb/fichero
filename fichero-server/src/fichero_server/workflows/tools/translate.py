"""Workflow translation tool (DeepL + fallback LLM providers)."""

from __future__ import annotations

from typing import Any

from fichero_server.llm import LLMConfig, translate_text
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    LLMToolConfig,
    merge_config_schema,
    parse_output,
    apply_reference_matching,
    save_artifact,
    save_to_file,
)
from fichero_server.workflows.types import DataType, PortDef, State


TOOL_CONFIG = LLMToolConfig(
    artifact_type="translation",
    update_page_content=False,
    trigger_embedding=True,
    embedding_scope="translation",
    metadata_field="translation",
)

TRANSLATE_CONFIG = {
    "source_lang": {
        "type": "string",
        "default": "auto",
        "description": "Source language code (auto, nl, es, fr, ...)",
        "x-group": "primary",
    },
    "target_lang": {
        "type": "string",
        "default": "en",
        "description": "Target language code (en, nl, es, fr, ...)",
        "x-group": "primary",
    },
}

TRANSLATE_INPUT_PORTS = [
    PortDef(
        id="text",
        name="Text",
        port_type="input",
        data_type=DataType.TEXT,
        required=True,
        description="Source text to translate.",
    )
]


@register_tool(
    name="translate",
    display_name="Translate",
    description="Translate text from source_lang to target_lang.",
    category="llm",
    icon="character.book.closed",
    color="teal",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=False,
    input_ports=TRANSLATE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, TRANSLATE_CONFIG),
    default_prompt="Translate source text faithfully.",
    sort_order=14,
)
async def translate(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    text = str(inputs.get("text", "") or "")
    if not text.strip():
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "error": "No text provided",
        }

    source_lang = str(inputs.get("source_lang", "auto") or "auto")
    target_lang = str(inputs.get("target_lang", "en") or "en")

    translated = await translate_text(
        text,
        source_lang=source_lang,
        target_lang=target_lang,
        config=llm_config,
    )

    output_format = inputs.get("output_format", "text")
    output_options = {
        "choices": inputs.get("choices"),
        "max_words": inputs.get("max_words"),
        "max_items": inputs.get("max_items"),
    }
    parsed = parse_output(translated, output_format, output_options)
    reference_values = inputs.get("reference_values")
    if reference_values:
        parsed = apply_reference_matching(parsed, reference_values)

    result = {
        "text": translated,
        "value": parsed,
    }
    artifact_ids: list[str] = []
    output_files: list[str] = []

    documents = inputs.get("documents", [])
    library_path = state.get("library_path", "")
    if inputs.get("save_to_db", True) and library_path and documents:
        for doc in documents[:1]:
            if isinstance(doc, dict) and doc.get("id"):
                artifact_id = await save_artifact(
                    document_id=doc["id"],
                    file_path=doc.get("path"),
                    content=translated,
                    data=parsed if isinstance(parsed, dict) else None,
                    library_path=library_path,
                    llm_config=llm_config,
                    task_id=state.get("task_id"),
                    tool_config=TOOL_CONFIG,
                    metadata_field=inputs.get("metadata_field"),
                    custom_metadata={
                        "source_lang": source_lang,
                        "target_lang": target_lang,
                    },
                )
                if artifact_id:
                    artifact_ids.append(artifact_id)
                    result["artifact_id"] = artifact_id

    if inputs.get("save_to_file", False) and library_path:
        doc_id = None
        file_path_for_save = None
        first_doc = documents[0] if documents else None
        if isinstance(first_doc, dict):
            doc_id = first_doc.get("id")
            file_path_for_save = first_doc.get("path")
        output_path = await save_to_file(
            content=translated,
            data=parsed if isinstance(parsed, dict) else None,
            library_path=library_path,
            document_id=doc_id,
            file_path=file_path_for_save,
            tool_config=TOOL_CONFIG,
            output_format=output_format,
        )
        if output_path:
            output_files.append(output_path)
            result["output_file"] = output_path

    return {
        "text": translated,
        "value": parsed,
        "texts": [translated],
        "values": [parsed],
        "results": [result],
        "artifacts": artifact_ids,
        "output_files": output_files,
    }

