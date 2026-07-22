"""Language identification workflow tool (#756).

Deterministic (no LLM call): chunk text, detect language per chunk,
then aggregate top languages with confidence and counts.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fichero.llm import LLMConfig
from fichero.llm.multilingual import detect_language, SUPPORTED_LANGUAGES
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    LLMToolConfig,
    merge_config_schema,
    save_artifact,
)
from fichero.workflows.types import DataType, PortDef, State


TOOL_CONFIG = LLMToolConfig(
    artifact_type="language_identification",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="language_detection",
)

LANGUAGE_IDENTIFICATION_CONFIG = {
    "chunk_size_chars": {
        "type": "integer",
        "default": 1200,
        "description": "Approximate chunk size for per-section language detection",
    },
    "max_languages": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of languages to return",
    },
}

LANGUAGE_INPUT_PORTS = [
    PortDef(
        id="text",
        name="Text",
        port_type="input",
        data_type=DataType.TEXT,
        required=True,
        description="Input text to detect language for",
    ),
    *BASE_INPUT_PORTS,
]


def _split_text(text: str, chunk_size_chars: int) -> list[str]:
    if not text:
        return []
    if chunk_size_chars <= 0 or len(text) <= chunk_size_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in (part.strip() for part in text.split("\n\n")):
        if not para:
            continue
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= chunk_size_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(para) <= chunk_size_chars:
            current = para
            continue
        for i in range(0, len(para), chunk_size_chars):
            chunks.append(para[i:i + chunk_size_chars])
    if current:
        chunks.append(current)
    return chunks or [text]


def _to_markdown(primary: str, languages: list[dict[str, Any]], model: str) -> str:
    lines = [
        "# Language Identification",
        "",
        f"- Primary language: `{primary}`",
        f"- Detector: `{model}`",
        "",
        "| Language | Confidence | Chunk Count |",
        "|---|---:|---:|",
    ]
    for item in languages:
        lines.append(
            f"| {item['code']} | {item['confidence']:.3f} | {item['chunk_count']} |"
        )
    return "\n".join(lines)


@register_tool(
    name="language_identification",
    display_name="Language Identification",
    description="Detect language(s) in a document and output aggregate metadata",
    category="llm",
    icon="globe",
    color="teal",
    uses_llm=False,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=LANGUAGE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema({}, LANGUAGE_IDENTIFICATION_CONFIG),
    sort_order=23,
)
async def language_identification(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    text = inputs.get("text", "") or ""
    documents = inputs.get("documents", []) or []
    if not text.strip():
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No text provided",
        }

    chunk_size = int(inputs.get("chunk_size_chars", 1200) or 1200)
    max_languages = max(1, int(inputs.get("max_languages", 5) or 5))
    chunks = _split_text(text, chunk_size)

    by_lang_conf: dict[str, list[float]] = defaultdict(list)
    for chunk in chunks:
        result = detect_language(chunk)
        by_lang_conf[result.language].append(float(result.confidence))

    if not by_lang_conf:
        by_lang_conf["en"].append(0.0)

    aggregated: list[dict[str, Any]] = []
    for code, confidences in by_lang_conf.items():
        aggregated.append(
            {
                "code": code,
                "language": SUPPORTED_LANGUAGES.get(code, code),
                "confidence": sum(confidences) / max(len(confidences), 1),
                "chunk_count": len(confidences),
            }
        )
    aggregated.sort(key=lambda item: (item["chunk_count"], item["confidence"]), reverse=True)
    languages = aggregated[:max_languages]
    primary = languages[0]["code"]

    payload = {
        "primary_language": primary,
        "languages": languages,
        "model": "multilingual.detect_language",
        "chunk_size_chars": chunk_size,
        "chunks_analyzed": len(chunks),
    }
    markdown = _to_markdown(primary, languages, payload["model"])

    artifact_ids: list[str] = []
    if inputs.get("save_to_db", True) and documents and state.get("library_path"):
        doc = documents[0] if isinstance(documents[0], dict) else {}
        artifact_id = await save_artifact(
            document_id=doc.get("id"),
            file_path=doc.get("path"),
            content=markdown,
            data=payload,
            library_path=state.get("library_path", ""),
            llm_config=llm_config,
            task_id=state.get("task_id"),
            tool_config=TOOL_CONFIG,
            metadata_field=inputs.get("metadata_field") or "language_detection",
        )
        if artifact_id:
            artifact_ids.append(artifact_id)

    return {
        "text": markdown,
        "value": payload,
        "texts": [markdown],
        "values": [payload],
        "results": [{"text": markdown, "value": payload}],
        "artifacts": artifact_ids,
    }

