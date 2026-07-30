"""
Similarity Tool

Computes similarity scores between two or more images.
Like compare, processes multiple images together (not batch).
Returns numeric scores by aspect.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fichero_server.db import db_manager
from fichero_server.models import Artifact
from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.catalogue import _resolve_write_target
from fichero_server.workflows.tools.llm_base import (
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
    build_context_section,
)
from fichero_server.workflows.types import DataType, PortDef
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    file_to_data_uri,
)
from fichero_server.llm import vision, LLMConfig

logger = logging.getLogger(__name__)

_SIMILARITY_OUTPUT_PORTS = merge_ports(
    BASE_OUTPUT_PORTS,
    [
        PortDef(
            id="clusters",
            name="Clusters",
            port_type="output",
            data_type=DataType.JSON,
            description="Typed same-document clusters.",
        )
    ],
)


class SimilarityAspectScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect: str
    score: float


class SameDocumentCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    member_document_ids: list[str] = Field(min_length=1)
    similarity_score: float = Field(ge=0.0, le=1.0)


class _RawSameDocumentCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    member_indexes: list[int] = Field(min_length=1)
    similarity_score: float = Field(ge=0.0, le=1.0)


class SameDocumentClusterResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_similarity: float
    aspect_scores: list[SimilarityAspectScore] = Field(default_factory=list)
    most_similar: str
    most_different: str
    notes: str
    same_document_clusters: list[SameDocumentCluster] = Field(min_length=1)


class _RawSimilarityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_similarity: float
    aspect_scores: list[SimilarityAspectScore] = Field(default_factory=list)
    most_similar: str
    most_different: str
    notes: str
    same_document_clusters: list[_RawSameDocumentCluster] = Field(min_length=1)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="similarity",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
)

SIMILARITY_CONFIG = {
    "aspects": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["content", "composition", "color", "style"],
        "description": "Aspects to score",
    },
    "scale": {
        "type": "string",
        "enum": ["percentage", "1-10", "1-5"],
        "default": "percentage",
        "description": "Score scale",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(aspects: list[str], scale: str) -> str:
    """Build the similarity scoring prompt."""
    aspects_str = ", ".join(aspects)

    scale_text = {
        "percentage": "Score each aspect as a percentage (0-100, where 100 = identical)",
        "1-10": "Score each aspect from 1 (completely different) to 10 (identical)",
        "1-5": "Score each aspect from 1 (completely different) to 5 (identical)",
    }.get(scale, "Score each aspect as a percentage (0-100)")

    return f"""Compare these images and score their similarity.

{scale_text}

Score these aspects: {aspects_str}

Also provide an overall similarity score.

Also group images that are the same underlying document (duplicates, alternate scans,
alternate photos, near-identical variants). Consider both visual appearance and visible
text content. Every image must appear in exactly one same-document cluster.

Return as JSON:
{{
    "overall_similarity": <score>,
    "aspect_scores": [
        {{"aspect": "<aspect>", "score": <score>}}
    ],
    "most_similar": "<which aspect is most similar>",
    "most_different": "<which aspect is most different>",
    "notes": "<brief explanation of key differences>",
    "same_document_clusters": [
        {{
            "cluster_id": "cluster-1",
            "member_indexes": [0, 1],
            "similarity_score": 0.98
        }}
    ]
}}

Return ONLY valid JSON."""


def build_similarity_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    aspects = config.get("aspects", ["content", "composition", "color", "style"])
    scale = config.get("scale", "percentage")
    return _build_prompt(aspects, scale)


def _doc_text(doc: dict[str, Any]) -> str:
    page_content = doc.get("page_content")
    if isinstance(page_content, str) and page_content.strip():
        return page_content.strip()
    metadata = doc.get("metadata")
    if isinstance(metadata, dict):
        transcription = metadata.get("transcription")
        if isinstance(transcription, str) and transcription.strip():
            return transcription.strip()
    return ""


def _document_context(documents: list[dict[str, Any]]) -> str:
    lines = ["Images are ordered as follows:"]
    for index, document in enumerate(documents):
        snippet = _doc_text(document)
        lines.append(
            f"- image {index}: doc_id={document['id']} name={document.get('name', '')!r}"
        )
        if snippet:
            lines.append(f"  text_snippet={snippet[:240]!r}")
    return "\n".join(lines) + "\n\n"


def _map_clusters(
    raw: _RawSimilarityResult,
    documents: list[dict[str, Any]],
) -> SameDocumentClusterResult:
    doc_ids = [str(document["id"]) for document in documents]
    clusters = [
        SameDocumentCluster(
            cluster_id=cluster.cluster_id,
            member_document_ids=[doc_ids[index] for index in cluster.member_indexes],
            similarity_score=cluster.similarity_score,
        )
        for cluster in raw.same_document_clusters
    ]
    covered = sorted(doc_id for cluster in clusters for doc_id in cluster.member_document_ids)
    expected = sorted(doc_ids)
    if covered != expected:
        raise ValueError(
            "same_document_clusters must cover each document exactly once"
        )
    return SameDocumentClusterResult(
        overall_similarity=raw.overall_similarity,
        aspect_scores=raw.aspect_scores,
        most_similar=raw.most_similar,
        most_different=raw.most_different,
        notes=raw.notes,
        same_document_clusters=clusters,
    )


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="similarity",
    display_name="Similarity",
    description="Score image similarity",
    category="vision",
    icon="square.on.square.dashed",
    color="orange",
    uses_llm=True,
    supports_batch=False,  # Processes all files together
    supports_structured_output=True,
    # #4345: the tool json-parses the vision response to build clusters, so an
    # OCR-only vision model (the keyless factory default) can never satisfy it.
    requires_generative_model=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=_SIMILARITY_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, SIMILARITY_CONFIG),
    default_prompt=_build_prompt(
        ["content", "composition", "color", "style"], "percentage"
    ),
    prompt_builder=build_similarity_prompt,
    sort_order=29,
)
async def similarity(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Score similarity between multiple images."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = list(inputs.get("documents") or [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")
    library_path = state.get("library_path", "")
    save_to_db = inputs.get("save_to_db", True)

    if isinstance(files, str):
        files = [files]

    if len(files) < 2:
        raise ValueError("Similarity requires at least 2 images")
    if len(documents) != len(files):
        raise ValueError("Similarity clustering requires documents aligned to files")

    aspects = inputs.get("aspects", ["content", "composition", "color", "style"])
    scale = inputs.get("scale", "percentage")
    max_image_dimension = inputs.get("max_image_dimension", 1024)
    temperature = inputs.get("temperature")
    max_tokens = inputs.get("max_tokens")

    prompt = inputs.get("prompt") or _build_prompt(aspects, scale)

    # Build context
    context_section = build_context_section(context, input_metadata)
    final_prompt = f"{context_section}{_document_context(documents)}{prompt}"

    # Override LLMConfig
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    image_uris = [
        file_to_data_uri(f, max_dimension=max_image_dimension) for f in files
    ]
    if not image_uris:
        raise ValueError("Similarity clustering requires image inputs")

    response = await vision(
        images=image_uris,
        prompt=final_prompt,
        config=effective_config,
    )

    raw = _RawSimilarityResult.model_validate(json.loads(response))
    parsed = _map_clusters(raw, documents)
    parsed_dict = parsed.model_dump(mode="json")
    artifact_ids: list[str] = []

    if save_to_db and library_path:
        container = _resolve_write_target(state.get("selected_doc_ids") or [], library_path)
        if container is None:
            raise ValueError("Similarity clustering could not resolve a write target")
        db = db_manager.get_database(library_path)
        artifact = Artifact(
            document_id=container.id,
            artifact_type=TOOL_CONFIG.artifact_type,
            content=response,
            data=parsed_dict,
            provider=getattr(effective_config, "provider", None),
            model=getattr(effective_config, "model", None),
            run_id=state.get("task_id"),
        )
        db.save(artifact)
        artifact_ids.append(artifact.id)

    return {
        "text": response,
        "value": parsed_dict,
        "texts": [response],
        "values": [parsed_dict],
        "results": [{"files": files, "text": response, "value": parsed_dict}],
        "clusters": parsed_dict["same_document_clusters"],
        "artifacts": artifact_ids,
    }
