"""
LLM Tools Base Module

Shared logic for all LLM-based tools (vision, text processing, entity extraction, etc.)
Each tool is a thin wrapper that provides:
- Default prompt
- Artifact type name
- Config options

This module provides:
- Base port and config schemas (inherited by all tools)
- Output format constraints and parsing
- Reference value matching
- Context injection
- Artifact saving
- Consistent error handling

Inheritance model:
- llm_base.py: BASE_CONFIG_SCHEMA, BASE_INPUT_PORTS, BASE_OUTPUT_PORTS
- vision_base.py: VISION_CONFIG_SCHEMA = BASE + vision-specific
- Individual tools: merge their specific config with parent
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from dataclasses import dataclass
from fichero_server.core.timeutil import utc_now
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero_server.llm import LLMConfig

from fichero_server.media.ocr_geometry import OCRGeometryResult
from fichero_server.workflows.types import PortDef, DataType
from fichero_server.workflows.tools._doc_lookup import find_document_by_path
from fichero_server.workflows.tools.llm_prompting import (  # noqa: F401 (re-exported)
    apply_reference_matching,
    build_context_section,
    build_output_constraint,
    build_reference_section,
    build_thinking_preamble,
    match_to_reference,
    parse_output,
)

logger = logging.getLogger(__name__)


class ArtifactLookupError(Exception):
    """The artifact result-cache lookup could not run to completion.

    Raised by find_existing_artifact when the underlying DB read itself
    errors (transient cross-connection read race, DuckDB hiccup, …) — as
    opposed to running cleanly and finding nothing. The distinction matters:
    a clean "found nothing" is a real cache MISS and returns None, but a
    failed lookup must NOT be silently reported as a miss, because that
    re-runs the full paid vision/LLM call while hiding the fault (#2511).
    Callers catch this, log loudly that they could not consult the cache,
    and proceed to re-run (the lesser, visible evil) rather than crash.
    """


# =============================================================================
# Base Port Definitions (inherited by all tools)
# =============================================================================

BASE_INPUT_PORTS = [
    PortDef(
        id="context",
        name="Context",
        port_type="input",
        data_type=DataType.ANY,
        required=False,
        description="Previous text/transcription",
    ),
    PortDef(
        id="metadata",
        name="Metadata",
        port_type="input",
        data_type=DataType.JSON,
        required=False,
        description="Existing metadata",
    ),
    PortDef(
        id="documents",
        name="Documents",
        port_type="input",
        data_type=DataType.JSON,
        required=False,
        description="Document metadata",
    ),
]

BASE_OUTPUT_PORTS = [
    PortDef(
        id="text",
        name="Text",
        port_type="output",
        data_type=DataType.TEXT,
        description="Raw text response",
    ),
    PortDef(
        id="value",
        name="Value",
        port_type="output",
        data_type=DataType.ANY,
        description="Parsed value",
    ),
    PortDef(
        id="texts",
        name="Texts",
        port_type="output",
        data_type=DataType.ARRAY,
        description="Per-item texts",
    ),
    PortDef(
        id="values",
        name="Values",
        port_type="output",
        data_type=DataType.ARRAY,
        description="Per-item values",
    ),
    PortDef(
        id="results",
        name="Results",
        port_type="output",
        data_type=DataType.JSON,
        description="Full results",
    ),
    PortDef(
        id="records",
        name="Records",
        port_type="output",
        data_type=DataType.ARRAY,
        description="Per-document text records [{doc_id, text}, ...].",
    ),
    PortDef(
        id="artifacts",
        name="Artifacts",
        port_type="output",
        data_type=DataType.JSON,
        description="Artifact IDs",
    ),
]


# =============================================================================
# Base Config Schema (inherited by all tools)
# =============================================================================

BASE_CONFIG_SCHEMA = {
    # Provider selection (overrides workflow default)
    "provider_name": {
        "type": "string",
        "enum": [
            "openai",
            "anthropic",
            "google",
            "ollama",
            "lmstudio",
            "groq",
            "together",
            "deepseek",
            "mistral",
            "openrouter",
            "dashscope",
            "xai",
            "perplexity",
            "fireworks",
            "deepl",
        ],
        "description": "LLM provider",
        "x-group": "primary",
    },
    "model_name": {
        "type": "string",
        "description": "Model name",
        "x-group": "primary",
    },
    # LLM parameters
    "temperature": {
        "type": "number",
        "default": 0.7,
        "min": 0,
        "max": 2,
        "description": "Creativity",
        "x-group": "advanced",
    },
    "max_tokens": {
        "type": "integer",
        "default": 2048,
        "description": "Max response",
        "x-group": "advanced",
    },
    # Output format
    "output_format": {
        "type": "string",
        "enum": ["text", "boolean", "choice", "number", "words", "list", "json"],
        "default": "text",
        "description": "Response format",
        "x-group": "output",
    },
    "choices": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Valid choices",
        "x-hidden": True,
    },
    "max_words": {
        "type": "integer",
        "default": 50,
        "description": "Word limit",
        "x-group": "output",
    },
    "max_items": {
        "type": "integer",
        "default": 10,
        "description": "List max items",
        "x-group": "output",
    },
    # Reference values
    "reference_values": {
        "type": "object",
        "description": "Known values to match",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
        "x-hidden": True,
    },
    "match_mode": {
        "type": "string",
        "enum": ["prefer", "strict", "inform"],
        "default": "prefer",
        "description": "Match mode",
        "x-group": "output",
    },
    # Storage
    "metadata_field": {
        "type": "string",
        "description": "Save to field",
        "x-group": "advanced",
    },
    "save_to_db": {
        "type": "boolean",
        "default": True,
        "description": "Save to library",
        "x-group": "advanced",
    },
    "save_to_file": {
        "type": "boolean",
        "default": False,
        "description": "Export to file",
        "x-group": "advanced",
    },
    # Quality gate (#1029) — when on, the builder aborts the run if this
    # node's text output is garbage (box glyphs / mostly [ilegible]),
    # instead of advancing the pipeline on unusable output. Stops on
    # *failure*, not on empty output. Inherited by every node.
    "quality_gate": {
        "type": "boolean",
        "default": True,
        "description": "Stop the run if output is unreadable",
        "x-group": "advanced",
    },
    # Thinking mode
    "thinking_mode": {
        "type": "string",
        "enum": ["off", "short", "medium", "long"],
        "default": "off",
        "description": "Chain-of-thought reasoning depth",
        "x-group": "primary",
    },
    # Custom prompt override
    "prompt": {
        "type": "string",
        "description": "Custom prompt",
        "x-group": "primary",
    },
    # Long-input handling (#801): split large merged text into chunks,
    # summarize each chunk, then synthesize once.
    "chunk_size_chars": {
        "type": "integer",
        "default": 0,
        "description": "Chunk large input text above this character budget (0=auto)",
        "x-group": "advanced",
    },
}


# =============================================================================
# Schema Merge Helpers
# =============================================================================


def merge_config_schema(*schemas: dict) -> dict:
    """Merge multiple config schemas, later ones override earlier.

    Usage:
        TOOL_CONFIG = merge_config_schema(BASE_CONFIG_SCHEMA, VISION_CONFIG_SCHEMA, MY_TOOL_CONFIG)
    """
    result = {}
    for schema in schemas:
        result.update(schema)
    return result


def merge_ports(*port_lists: list[PortDef]) -> list[PortDef]:
    """Merge port lists, avoiding duplicates by id. Later ports override earlier.

    Usage:
        input_ports = merge_ports(BASE_INPUT_PORTS, [files_port])
    """
    seen: dict[str, PortDef] = {}
    for ports in port_lists:
        for p in ports:
            seen[p.id] = p
    return list(seen.values())


def extract_base_config(inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract all BASE_CONFIG values from inputs dict.

    Useful for passing to process_text/process_vision.
    """
    return {
        "temperature": inputs.get("temperature"),
        "max_tokens": inputs.get("max_tokens"),
        "output_format": inputs.get("output_format", "text"),
        "output_options": {
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items"),
        },
        "reference_values": inputs.get("reference_values"),
        "match_mode": inputs.get("match_mode", "prefer"),
        "context": inputs.get("context"),
        "input_metadata": inputs.get("metadata"),
        "save_to_db": inputs.get("save_to_db", True),
        "metadata_field": inputs.get("metadata_field"),
        "chunk_size_chars": inputs.get("chunk_size_chars"),
    }


# =============================================================================
# Tool Configuration
# =============================================================================


@dataclass
class LLMToolConfig:
    """Configuration for an LLM tool."""

    # What this tool produces
    artifact_type: str

    # Whether to update Document.page_content (makes it searchable)
    update_page_content: bool = False

    # Whether to trigger re-embedding after update
    trigger_embedding: bool = False

    # Embedding scope for vector records ("passage" for document content,
    # "translation" for translation artifacts, etc.)
    embedding_scope: str = "passage"

    # Default metadata field to update (None = don't update metadata)
    metadata_field: str | None = None

    # If True (default), skip the LLM call when an artifact of the same
    # artifact_type already exists for the input document. Makes workflows
    # idempotent: re-running Catalogue on a folder with half the files
    # already transcribed only transcribes the remaining half. Users can
    # disable per-node in the config to force a re-run.
    skip_if_artifact_exists: bool = True


def find_existing_artifact(
    document_id: str | None,
    file_path: str | None,
    artifact_type: str,
    library_path: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> Any | None:
    """Return the most recent artifact of the given type for a document, or None.

    The cache key is (document_id, artifact_type, provider, model) when
    provider/model are supplied. Matching on provider/model matters because
    running Transcribe with qwen-vl-3.5 and then with qwen-vl-3.6v should
    produce *two* artifacts (one per model) — not silently reuse the 3.5
    result when the user asked for 3.6v. Callers that don't care about
    model identity can omit both and get the legacy behaviour (newest of
    any provider/model for this artifact_type).
    """
    if not library_path or not artifact_type:
        return None

    try:
        from fichero_server.db import db_manager
        from fichero_server.models import Document as _Document, Artifact as _Artifact

        db = db_manager.get_database(library_path)

        # Resolve the document id to dedup against. Artifacts are keyed by
        # document_id, so when the caller passes an explicit id we look up
        # artifacts directly — no need to fetch the Document row, which can
        # transiently miss during the concurrent per-page fan-out (each thread
        # has its own DuckDB connection; MVCC snapshot skew) and would make us
        # wrongly create a duplicate. Only fall back to file_path when no
        # document_id was given; resolving a missing explicit id via file_path
        # would silently return the parent PDF for page-child ids (#2430).
        resolved_doc_id = None
        if document_id:
            resolved_doc_id = document_id
        elif file_path:
            docs = db.query(_Document, path=file_path)
            if docs:
                resolved_doc_id = docs[0].id
        if not resolved_doc_id:
            return None

        artifacts = list(
            db.query(_Artifact, document_id=resolved_doc_id, artifact_type=artifact_type)
        )
        if provider is not None:
            artifacts = [a for a in artifacts if getattr(a, "provider", None) == provider]
        if model is not None:
            artifacts = [a for a in artifacts if getattr(a, "model", None) == model]
        if not artifacts:
            return None

        # Prefer the newest artifact by created_at.
        artifacts.sort(key=lambda a: getattr(a, "created_at", 0) or 0, reverse=True)
        return artifacts[0]
    except Exception as exc:
        # A clean "found nothing" already returned None above. Reaching here
        # means the DB read itself FAILED (db.get/db.query raised) — we do NOT
        # know whether a cached artifact exists. Reporting that as a miss
        # (return None) would silently re-run the full paid call while hiding
        # the fault. Surface it loudly as a distinct error so the caller can
        # log "could not check cache" and decide to re-run, never pretend-miss
        # (#2511, no silent fallback).
        logger.error(f"find_existing_artifact lookup FAILED (not a miss): {exc}")
        raise ArtifactLookupError(str(exc)) from exc


# =============================================================================
# Database Operations
# =============================================================================


async def save_artifact(
    document_id: str | None,
    file_path: str | None,
    content: str,
    data: dict | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
    tool_config: LLMToolConfig,
    *,
    ocr_geometry: OCRGeometryResult | None = None,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
    document: object | None = None,
) -> str | None:
    """Save LLM result to database.

    Creates an Artifact and optionally updates Document fields.

    Args:
        document_id: Document ID (if known)
        file_path: File path (if no document_id)
        content: Text content for artifact
        data: Structured data for artifact (optional)
        library_path: Path to library database
        llm_config: LLM config (for recording provider/model)
        task_id: Workflow task ID
        tool_config: Tool-specific configuration
        metadata_field: Override where to save in metadata
        custom_metadata: Additional key-value pairs to save

    Returns:
        Artifact ID if saved, None otherwise
    """
    if not library_path:
        return None

    # Validate a pass-through document dict UP FRONT, outside the catch-all
    # `try` below. That try is meant to absorb DB-write failures (artifact
    # insert / page_content promotion) and report them as a miss; if a caller
    # passes a malformed/partial dict, model_validate's ValidationError must
    # surface LOUD, not be swallowed as a silent None artifact loss. A None
    # document is fine (falls through to db.get); only a non-None dict that
    # fails validation must fail here. (#2513, no silent fallback)
    from fichero_server.models import Document

    if isinstance(document, dict):
        doc = Document.model_validate(document)
    else:
        doc = document

    # Offload the synchronous DB-write + embed sequence off the event loop in a
    # SINGLE thread hop. The shared Database connection is guarded by a
    # re-entrant threading.RLock, so running this on a threadpool thread is safe
    # (the lock serializes one-at-a-time access) and is consistent with the
    # FastAPI-threadpool design the lock was built for. Doing this here is what
    # lets per-file concurrency actually overlap — previously db.save / db.embed
    # ran ON the loop and pinned it, so nothing else could make progress while a
    # save was in flight (#2540). Behaviour is identical: same rows, same
    # per-page contract, same fail-loud return-None / raise semantics, all of
    # which live verbatim inside _save_artifact_sync.
    return await asyncio.to_thread(
        _save_artifact_sync,
        doc,
        document_id,
        file_path,
        content,
        data,
        library_path,
        llm_config,
        task_id,
        tool_config,
        metadata_field,
        custom_metadata,
        ocr_geometry,
    )


def _save_artifact_sync(
    doc: object | None,
    document_id: str | None,
    file_path: str | None,
    content: str,
    data: dict | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
    tool_config: LLMToolConfig,
    metadata_field: str | None,
    custom_metadata: dict | None,
    ocr_geometry: OCRGeometryResult | None,
) -> str | None:
    """Synchronous DB-write + embed core of :func:`save_artifact`.

    Runs OFF the event loop via ``asyncio.to_thread`` (see caller). All the
    blocking work — ``db.save`` (artifact + doc), ``db.embed`` (ONNX inference),
    and metadata decoration — happens here on a threadpool thread. The shared
    Database connection's re-entrant RLock serializes concurrent threads, so
    this is safe. The per-page contract (#2430/#2523) and fail-loud /
    return-None / raise semantics are unchanged from the original inline body.
    """
    from fichero_server.models import Artifact, Status

    artifact_id: str | None = None
    try:
        from fichero_server.db import db_manager
        from fichero_server.models import Document

        db = db_manager.get_database(library_path)

        if doc is None and document_id:
            doc = db.get(Document, document_id)
        # Only use file_path fallback when no document_id was given — if an
        # explicit id was provided but not found, silently resolving to whatever
        # file_path maps to (e.g. the parent PDF) would write the artifact to
        # the wrong document (#2430 per-page fan-out regression).
        if not doc and file_path and not document_id:
            doc = find_document_by_path(db, Document, file_path)

        # The per-page fan-out passes the page-child document through
        # (document=) so we never re-fetch it by id across threads — that is
        # what eliminates the #2430 race. If we STILL have no document here it
        # genuinely cannot be resolved; do NOT fabricate an artifact keyed on an
        # unverified id (that would orphan it, or — via the removed file_path
        # fallback — mis-route to the parent PDF). Fail loud + return None so
        # the miss is visible, never a silent substitute. (#2430)
        if doc is None:
            logger.warning(
                "Document not found for artifact save: id=%s path=%s — "
                "skipping (no silent orphan / parent reroute)",
                document_id,
                file_path,
            )
            return None
        resolved_doc_id = doc.id

        # Provenance (#4313): the live runner puts the run's thread_id into
        # state as task_id, so run_id ties the artifact to its workflow run;
        # the builder's node wrappers stamp the executing node into the
        # node-context contextvar (copied into this asyncio.to_thread worker),
        # so step_name/workflow_id survive the parallel fan-out; sequence is a
        # per-run monotonic counter (DB-seeded so resume keeps numbering).
        from fichero_server.workflows.node_context import (
            get_current_node,
            next_artifact_sequence,
        )

        node_ctx = get_current_node()
        step_name = node_ctx.node_id if node_ctx else None
        artifact_workflow_id = (node_ctx.workflow_id or None) if node_ctx else None
        sequence: int | None = None
        if task_id:

            def _seed_from_db() -> int:
                try:
                    return max(
                        (a.sequence or 0 for a in db.query(Artifact, run_id=task_id)),
                        default=0,
                    )
                except Exception:
                    return 0

            sequence = next_artifact_sequence(task_id, seed_fn=_seed_from_db)

        # Create Artifact
        artifact = Artifact(
            document_id=resolved_doc_id,
            source_document_id=resolved_doc_id,
            artifact_type=tool_config.artifact_type,
            content=content,
            data=data,
            ocr_geometry=ocr_geometry,
            provider=llm_config.provider if hasattr(llm_config, "provider") else None,
            model=llm_config.model if hasattr(llm_config, "model") else None,
            run_id=task_id,
            step_name=step_name,
            workflow_id=artifact_workflow_id,
            sequence=sequence,
        )
        db.save(artifact)
        artifact_id = artifact.id
        logger.info(f"Created {tool_config.artifact_type} artifact {artifact_id}")

        # Update Document.page_content if configured — but NEVER clobber
        # user-edited page_content. The API update route sets
        # metadata["page_content_user_edited_at"] whenever a user saves
        # an edit to page_content; if that flag is present, a transcription
        # or other tool that produced this artifact should leave the text
        # alone. The artifact is still saved so the result is discoverable
        # on the Artifacts tab — just not promoted over the user's edit.
        # See issue #672. Guarded on `doc is not None`: when the row wasn't
        # visible on this connection (concurrent fan-out, #2430) the artifact
        # above is still saved on the right page; only this doc-side update,
        # which needs the live row, is deferred to a later/visible pass.
        #
        # The check itself now lives in curation_guard: Catalogue wrote
        # container.page_content directly and never asked this question, so
        # the guard held for pages and not for the flagship path. One function,
        # one answer, both callers.
        if doc is not None:
            from fichero_server.workflows.curation_guard import (
                page_content_is_user_edited,
            )

            # Ensure metadata is a mutable dict (NULL in DB parses as None)
            if not isinstance(doc.metadata, dict):
                doc.metadata = {}
            user_edited = page_content_is_user_edited(doc)
            if tool_config.update_page_content and not user_edited:
                doc.page_content = content
                # In-progress, NOT completed: a content-producing node may be
                # one of several pipeline steps. The workflow boundary owns the
                # flip to completed once the whole run finishes, so the green
                # check no longer appears after just the first step (#1282). See
                # fichero_server.workflows.completion.complete_run_documents.
                doc.status = Status.processing
                doc.updated_at = utc_now()
                db.save(doc)

                # Broadcast the MID-RUN page_content write to the library
                # change-stream (#4318): until now document.updated was emitted
                # only at the run boundary (completion.finalize_run_documents),
                # so an open window showed fresh transcription text only after
                # reselecting the page. Best-effort by contract — the emit
                # helper swallows failures so it can never fail the save above.
                from fichero_server.workflows.tools._workflow_change_emit import (
                    emit_workflow_document_changes_for_db,
                )

                parent_id = getattr(doc, "parent_id", None)
                emit_workflow_document_changes_for_db(
                    db,
                    document_ids=[resolved_doc_id],
                    document_parents=(
                        {resolved_doc_id: parent_id}
                        if isinstance(parent_id, str) and parent_id
                        else None
                    ),
                    run_id=task_id,
                )

                if tool_config.trigger_embedding:
                    # Embedding is a best-effort TAIL: the artifact and the
                    # promoted page_content are already durably saved above, so
                    # the result is not lost. A failed embed must NOT fail the
                    # whole save (that would mask a successful write and report
                    # false failure) — but it must be LOUD, never silently
                    # swallowed, so a missing/stale vector is diagnosable
                    # (#2510, no silent fallback).
                    try:
                        db.embed(doc)
                        logger.info(f"Updated page_content and embedding for {doc.id}")
                    except Exception as embed_exc:
                        logger.error(
                            "Embedding FAILED for %s after artifact + "
                            "page_content saved — save still SUCCEEDED "
                            "(best-effort embed tail): %s",
                            doc.id,
                            embed_exc,
                        )
            elif tool_config.trigger_embedding and not tool_config.update_page_content:
                # Artifact-content embedding (e.g. translations): embed the
                # artifact text with a scoped label so it's searchable alongside
                # the original document but distinguishable in results.  The
                # document's own passage embeddings are untouched — only the
                # artifact-scope vectors are added/deleted.
                try:
                    db.embed_artifact_content(
                        doc, content, artifact_id=artifact_id,
                        embedding_scope=tool_config.embedding_scope,
                    )
                    logger.info(
                        "Embedded artifact %s content for %s (scope=%s)",
                        artifact_id, doc.id, tool_config.embedding_scope,
                    )
                except Exception as embed_exc:
                    logger.error(
                        "Artifact embedding FAILED for %s — "
                        "artifact saved but not searchable: %s",
                        artifact_id, embed_exc,
                    )
            elif tool_config.update_page_content and user_edited:
                logger.info(
                    f"Preserved user-edited page_content on {doc.id}; "
                    f"artifact {artifact_id} saved but not promoted."
                )

    except Exception as e:
        # Reaching here means a CORE write failed: the artifact insert (step 1)
        # or the page_content promotion (step 2, db.save(doc)). The best-effort
        # embed tail (step 3) is caught above and never lands here. Returning
        # artifact_id now would record FALSE SUCCESS — the doc content was not
        # promoted, nothing was rolled back, and the caller would believe the
        # operation completed (#2510). Surface the failure instead so the caller
        # (per-file loop / workflow node) records a real error and can retry.
        #
        # NOTE: without a Database transaction boundary (#2508) the step-1
        # artifact row may already be committed when step 2 fails; we cannot
        # atomically roll it back here. Making artifact+doc writes truly atomic
        # is the systemic #2508 work — this fix only stops the false-success
        # report, which is the minimal no-silent-fallback change.
        logger.error(f"Failed to save artifact (core write, surfacing): {e}")
        raise

    # Metadata decoration is non-fatal — keep it isolated so it can never
    # hide a successful artifact + page_content save.
    try:
        final_metadata_field = metadata_field or tool_config.metadata_field
        if (final_metadata_field or custom_metadata) and doc is not None:
            if not isinstance(doc.metadata, dict):
                doc.metadata = {}
            if final_metadata_field:
                doc.metadata[final_metadata_field] = data if data else content[:1000]
            if custom_metadata:
                doc.metadata.update(custom_metadata)
            doc.updated_at = utc_now()
            db.save(doc)
    except Exception as meta_e:
        logger.warning(f"Metadata decoration failed for artifact {artifact_id}: {meta_e}")

    return artifact_id


async def save_file_artifact(
    file_path: str | None,
    content: str,
    document_id: str | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
    tool_config: LLMToolConfig,
    *,
    ocr_geometry: OCRGeometryResult | None = None,
    data: dict | None = None,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
    document: object | None = None,
) -> str | None:
    """File-oriented entry point to ``save_artifact`` for media/file tools.

    This is the SINGLE shared wrapper that the per-media-family tools (vision,
    audio, video) and file-keyed text tools (extract) all use. It exists so the
    per-page save contract — an explicit ``document_id`` means NO ``file_path``
    fallback; a genuine lookup miss FAILS LOUD (returns None, never reroutes to
    the parent PDF, #2430/#2523); the ``document=`` pass-through dodges the
    cross-thread re-fetch race — is enforced in exactly ONE place
    (``save_artifact`` above) and is never re-derived per family.

    The only family-specific convention it encodes is that file/media artifacts
    carry no structured ``data`` by default (``data=None``); markup tools may
    stamp a small typed payload (e.g. ``{"target_format": "svg"}``, #4329).
    Everything else is a straight pass-through. ``file_path`` is listed first
    because callers key on the source path, but every call site uses keyword
    arguments.
    """
    return await save_artifact(
        document_id=document_id,
        file_path=file_path,
        content=content,
        data=data,
        ocr_geometry=ocr_geometry,
        library_path=library_path,
        llm_config=llm_config,
        task_id=task_id,
        tool_config=tool_config,
        metadata_field=metadata_field,
        custom_metadata=custom_metadata,
        document=document,
    )


async def save_to_file(
    content: str,
    data: dict | None,
    library_path: str,
    document_id: str | None,
    file_path: str | None,
    tool_config: LLMToolConfig,
    output_format: str = "text",
) -> str | None:
    """Save LLM result to a file in the library package.

    Writes output to: {library_path}/storage/outputs/{id[:2]}/{id}_{type}.{ext}

    Args:
        content: Text content to save
        data: Structured data (saved as JSON if present)
        library_path: Path to library package
        document_id: Document ID for naming
        file_path: Source file path (fallback for naming)
        tool_config: Tool configuration (for artifact_type)
        output_format: Determines file extension

    Returns:
        Path to saved file, or None on failure
    """
    try:
        if not library_path:
            logger.warning("Cannot save to file: no library_path")
            return None

        # Determine document identifier for filename
        doc_id = document_id
        if not doc_id and file_path:
            # Use source filename as fallback
            doc_id = Path(file_path).stem

        if not doc_id:
            logger.warning("Cannot save to file: no document_id or file_path")
            return None

        # Determine extension
        if data or output_format == "json":
            ext = "json"
        elif output_format in ("list", "words"):
            ext = "txt"
        else:
            ext = "txt"

        # Build output path
        output_dir = Path(library_path) / "storage" / "outputs" / doc_id[:2]
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{doc_id}_{tool_config.artifact_type}.{ext}"

        # Write content
        if ext == "json" and data:
            output_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            output_file.write_text(content)

        logger.info(f"Saved {tool_config.artifact_type} to file: {output_file}")
        return str(output_file)

    except Exception as e:
        logger.error(f"Failed to save to file: {e}")
        return None


# =============================================================================
# Error Handling
# =============================================================================


@dataclass
class LLMResult:
    """Result from LLM processing with error handling."""

    text: str = ""
    value: Any = None
    error: str | None = None
    artifact_id: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


def create_error_result(
    error: str | Exception,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Create a standard error result dict.

    Args:
        error: Error message or exception
        file_path: Optional file path for context

    Returns:
        Error result dict
    """
    error_msg = str(error)

    result = {
        "text": "",
        "value": None,
        "error": error_msg,
    }

    if file_path:
        result["file"] = file_path

    logger.error(f"LLM processing error: {error_msg}")
    return result


def validate_inputs(
    required: dict[str, Any],
    optional: dict[str, tuple[Any, Any]] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Validate and normalize inputs.

    Args:
        required: Dict of required input names to values
        optional: Dict of optional input names to (value, default) tuples

    Returns:
        Tuple of (validated inputs dict, error message or None)
    """
    validated = {}

    # Check required inputs
    for name, value in required.items():
        if value is None or value == "" or value == []:
            return {}, f"Missing required input: {name}"
        validated[name] = value

    # Apply defaults for optional inputs
    if optional:
        for name, (value, default) in optional.items():
            validated[name] = value if value is not None else default

    return validated, None


# =============================================================================
# Shared Text Processing
# =============================================================================


_ON_DEVICE_CHUNK_SIZE = 12000
_ON_DEVICE_PROVIDERS = {"apple", "ollama", "lmstudio"}


def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks, preferring semantic boundaries."""
    if not text:
        return [""]
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    paragraphs = text.split("\n\n")

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(para) <= max_chars:
            current = para
            continue

        # Oversized paragraph: hard-split by character budget.
        for i in range(0, len(para), max_chars):
            chunks.append(para[i:i + max_chars])

    if current:
        chunks.append(current)
    return chunks or [text]


def _effective_chunk_size(
    text: str,
    llm_config: "LLMConfig",
    chunk_size_chars: int | None,
) -> int:
    """Resolve chunk threshold. Explicit value wins; otherwise auto for on-device."""
    if isinstance(chunk_size_chars, int):
        if chunk_size_chars > 0:
            return chunk_size_chars
        if chunk_size_chars < 0:
            return 0
    provider = (getattr(llm_config, "provider", "") or "").lower()
    if provider in _ON_DEVICE_PROVIDERS and len(text) > _ON_DEVICE_CHUNK_SIZE:
        return _ON_DEVICE_CHUNK_SIZE
    return 0


async def process_text(
    text: str,
    prompt: str,
    llm_config: LLMConfig,
    library_path: str,
    task_id: str | None,
    tool_config: LLMToolConfig,
    documents: list[dict] | None = None,
    *,
    # LLM parameters (from BASE_CONFIG_SCHEMA)
    temperature: float | None = None,
    max_tokens: int | None = None,
    # Output format (from BASE_CONFIG_SCHEMA)
    output_format: str = "text",
    output_options: dict | None = None,
    # Reference values (from BASE_CONFIG_SCHEMA)
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
    # Context (from BASE_CONFIG_SCHEMA)
    context: str | None = None,
    input_metadata: dict | None = None,
    # Thinking mode (from BASE_CONFIG_SCHEMA)
    thinking_mode: str = "off",
    # Storage (from BASE_CONFIG_SCHEMA)
    save_to_db: bool = True,
    save_to_file_flag: bool = False,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
    # Long-input chunking (from BASE_CONFIG_SCHEMA)
    chunk_size_chars: int | None = None,
) -> dict[str, Any]:
    """Shared text processing for all LLM text tools."""
    from fichero_server.llm import chat

    if not text:
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

    # Override LLMConfig with user values if provided
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    # Build context section
    context_section = build_context_section(context, input_metadata)

    # Build reference section
    ref_section = build_reference_section(reference_values, match_mode)

    # Build output constraint
    output_constraint = build_output_constraint(output_format, output_options)

    # Build thinking preamble
    thinking_preamble = build_thinking_preamble(thinking_mode)

    # System+user split (#815) — rules + role + context go to the
    # system channel; only the source text is the user prompt. Apple
    # Intelligence routes system → its authoritative Instructions
    # channel; non-Apple LangChain providers also benefit from a
    # proper system message. This shared site cascades to summarize,
    # entities, timeline, key_people, rewrite, sentiment, keywords,
    # questions, classify_text — every simple LLM tool.
    instructions = (
        f"{thinking_preamble}{context_section}{prompt}"
        f"{ref_section}{output_constraint}"
    ).strip()

    try:
        response: str
        effective_chunk_size = _effective_chunk_size(
            text=text,
            llm_config=effective_config,
            chunk_size_chars=chunk_size_chars,
        )
        if effective_chunk_size > 0 and len(text) > effective_chunk_size:
            chunks = _split_text_into_chunks(text, effective_chunk_size)
            logger.info(
                "process_text: chunking %s chars into %s chunks (size=%s)",
                len(text),
                len(chunks),
                effective_chunk_size,
            )
            chunk_notes: list[str] = []
            chunk_system = (
                "You are processing one section of a larger document. "
                "Extract the key facts and details relevant to the task. "
                "Respond in plain concise text."
            )
            for idx, chunk in enumerate(chunks):
                note = await chat(
                    f"Section {idx + 1} of {len(chunks)}:\n{chunk}",
                    config=effective_config,
                    system=chunk_system,
                )
                chunk_notes.append(note.strip())

            synthesis_input = "\n\n".join(
                f"Section {i + 1} notes:\n{note}" for i, note in enumerate(chunk_notes)
            )
            response = await chat(
                synthesis_input,
                config=effective_config,
                system=instructions,
            )
        else:
            response = await chat(
                text,
                config=effective_config,
                system=instructions,
            )

        # Parse output
        parsed = parse_output(response, output_format, output_options)

        # Apply reference matching
        if reference_values:
            parsed = apply_reference_matching(parsed, reference_values)

        result = {
            "text": response,
            "value": parsed,
        }

        # Save to database
        artifact_ids = []
        if save_to_db and library_path:
            # An empty write target is an ERROR, not a skip (#4404).
            #
            # This used to read `if save_to_db and library_path and documents:`
            # — so a tool that was told to persist, and had already spent the
            # provider call producing `response`, silently dropped it when
            # nothing resolved to attach it to. `summarize_folder` hit this on
            # every run: it declares a `folder_id` input port that no source
            # tool could fill (#4404), so `documents` was always empty and the
            # folder summary was generated, paid for, and discarded with no
            # error and no artifact — a run reporting success having produced
            # nothing, which is the #4283 shape.
            #
            # The same silence covered a second case: a `documents` list whose
            # entries carry no usable id. Both are checked here, because both
            # mean "the work is done and there is nowhere to put it".
            target = next(
                (
                    doc
                    for doc in documents or []
                    if isinstance(doc, dict) and doc.get("id")
                ),
                None,
            )
            if target is None:
                raise ValueError(
                    "process_text: nothing to attach the result to — "
                    f"save_to_db is on but no document with an id was "
                    f"resolved (got {len(documents or [])} candidate(s)). "
                    "The output was produced and would have been discarded. "
                    "Wire a document/container source into this node, or set "
                    "save_to_db=false if this node is not meant to persist."
                )
            for doc in [target]:
                if isinstance(doc, dict) and doc.get("id"):
                    artifact_id = await save_artifact(
                        document_id=doc["id"],
                        file_path=doc.get("path"),
                        content=response,
                        data=parsed if isinstance(parsed, dict) else None,
                        library_path=library_path,
                        llm_config=effective_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                        result["artifact_id"] = artifact_id

        # Save to file
        output_files = []
        if save_to_file_flag and library_path:
            doc_id = None
            file_path_for_save = None
            if documents:
                first_doc = documents[0] if documents else None
                if isinstance(first_doc, dict):
                    doc_id = first_doc.get("id")
                    file_path_for_save = first_doc.get("path")

            output_path = await save_to_file(
                content=response,
                data=parsed if isinstance(parsed, dict) else None,
                library_path=library_path,
                document_id=doc_id,
                file_path=file_path_for_save,
                tool_config=tool_config,
                output_format=output_format,
            )
            if output_path:
                output_files.append(output_path)
                result["output_file"] = output_path

        return {
            "text": response,
            "value": parsed,
            "texts": [response],
            "values": [parsed],
            "results": [result],
            "artifacts": artifact_ids,
            "output_files": output_files,
        }

    except Exception as e:
        logger.error(f"Text processing failed: {e}")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "error": str(e),
        }
