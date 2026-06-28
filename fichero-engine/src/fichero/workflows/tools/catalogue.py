"""
Catalogue Tool

Generates a structured archival catalogue entry for a folder of documents,
producing a rich nine-section output matching the reference format in the
Archivo Judicial de Medellín catalogue.docx exemplars.

Contract:
- Expects aggregated `text` input (from upstream Transcribe → implicit aggregate).
- Reads `state.selected_doc_ids` to determine the container (folder) on which
  to save the final artifact. If the selection is a single folder doc, save
  there. If it's a single PDF/file doc, save on that doc. If it's page docs,
  save on their parent PDF. Mixed selections resolve to the selected parent
  doc when possible.
- Produces one Artifact on the resolved doc with type="catalogue", containing:
    - content: markdown rendering of the nine sections (human-readable)
    - data:    parsed JSON matching the nine-section schema
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
)

from fichero.llm import LLMConfig, chat_with_fallback
from fichero.db import db_manager
from fichero.models import Document, DocType, Artifact
from fichero.workflows.tools._workflow_change_emit import emit_workflow_artifact_changes

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="catalogue",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field=None,
)

CATALOGUE_CONFIG = {
    "output_language": {
        "type": "string",
        "default": "auto",
        "description": (
            "Output language. 'auto' detects from the source text "
            "(English / Spanish today); explicit names like 'English' "
            "or 'Spanish' pin the language regardless of input."
        ),
        "x-group": "primary",
    },
    "claim_context_caps": {
        "type": "object",
        "default": {},
        "description": (
            "Per-section caps for the entity-context block fed to the "
            "narrative LLM. Keys: people, places, organizations, events, "
            "dates, keywords. Each value is the max items to include "
            "before the list is truncated with '(… +N more)'. Defaults: "
            "people=30, places=20, organizations=15, events=15, dates=30, "
            "keywords=30. Override only the sections you want to change. "
            "Useful on dense folders (100+ contributors) or sparse "
            "letters where you want to dial cap up/down. (#865)"
        ),
        "x-group": "advanced",
    },
    "hitl_on_ambiguous_grouping": {
        "type": "boolean",
        "default": False,
        "description": "Pause for confirmation when case grouping appears ambiguous",
        "x-group": "advanced",
    },
    "ambiguous_min_items": {
        "type": "integer",
        "default": 25,
        "description": "Minimum child documents before ambiguity HITL can trigger",
        "x-group": "advanced",
    },
}

CATALOGUE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description=(
                "Aggregated TRANSCRIPTION text — wire from aggregate.text "
                "(per-file transcriptions joined), NOT from the merge of "
                "cleanup outputs. The narrative LLM reads this as source "
                "material; pointing it at cleaned entity lists makes it "
                "summarise the cleanup output instead of the documents."
            ),
        ),
        PortDef(
            id="barrier",
            name="Barrier (sync)",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description=(
                "Optional dependency-only port. Wire merge_extracts here "
                "(or any other late node) to make catalogue wait for the "
                "cleanup chain to finish before it queries the DB for "
                "canonical entities. Value is ignored."
            ),
        ),
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt (ported from legacy Catalogue (English).jsonl)
# =============================================================================

# Schema template uses __LANG__ as the placeholder for the target language
# rather than the string "{output_language}" to avoid accidental collisions
# with future schema content that happens to contain the same literal.
_CATALOGUE_SCHEMA = """{
  "summary": "string — narrative summary, 150-300 words in __LANG__",
  "keywords": ["keyword1", "keyword2", "..."],
  "people": [
    {"name": "...", "context": "role and importance in __LANG__"}
  ],
  "dates": [
    {"date": "as written", "date_normalized": "YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD", "context": "..."}
  ],
  "legal_references": [
    {"name": "...", "context": "..."}
  ],
  "rivers": [
    {"name": "...", "alternative_spellings": ["..."], "context": "..."}
  ],
  "events": [
    {"event": "...", "context": "..."}
  ],
  "mines": [
    {"name": "...", "context": "..."}
  ],
  "properties": [
    {"name": "...", "context": "..."}
  ]
}"""


def _build_prompt(output_language: str) -> str:
    """Build the catalogue narrative prompt.

    Loaded from the versioned prompt registry (#816) at
    `resources/prompts/catalogue/narrative_v<N>.md`. Edit the latest
    version's frontmatter+body to tune; bump the filename when shipping
    a meaningful behavioural change so the prior version stays available
    for A/B comparison via the eval harness (#817).

    Adapted directly from the legacy Generic_Catalogue pipeline's final
    `library_catalogue_entry` step. Per-section typed entities (Dates /
    People / Events) are produced by separate Extract* nodes in the
    composable workflow — this tool's job is the catalogue *synthesis*,
    not the extraction.
    """
    from fichero.prompts import load_prompt
    return load_prompt(
        "catalogue", "narrative",
        output_language=output_language,
    )


def build_catalogue_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    output_language = config.get("output_language", "auto")
    if output_language.lower() in {"", "auto"}:
        output_language = "English"  # placeholder for prompt preview
    return _build_prompt(output_language)


# =============================================================================
# Rendering helpers
# =============================================================================


def _render_markdown(data: dict[str, Any]) -> str:
    """Render the nine-section JSON as a human-readable markdown document.

    Mirrors the structure of the reference .docx so researchers see something
    familiar. Sections with no content are skipped.
    """
    lines: list[str] = []

    summary = data.get("summary") or data.get("resumen")
    if summary:
        lines.append("## Summary\n")
        lines.append(str(summary))
        lines.append("")

    keywords = data.get("keywords") or data.get("palabras_clave")
    if keywords:
        lines.append("## Keywords\n")
        if isinstance(keywords, list):
            lines.append("; ".join(str(k) for k in keywords))
        else:
            lines.append(str(keywords))
        lines.append("")

    # column tuples are (english_key, legacy_spanish_key, header).
    def _table(
        section_keys: tuple[str, str], title: str,
        columns: list[tuple[str, str, str]],
    ) -> None:
        en_key, es_key = section_keys
        items = data.get(en_key) or data.get(es_key) or []
        if not items:
            return
        lines.append(f"## {title}\n")
        lines.append("| " + " | ".join(c[2] for c in columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for item in items:
            if not isinstance(item, dict):
                continue
            row = []
            for en, es, _ in columns:
                val = item.get(en) if en in item else item.get(es, "")
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                row.append(str(val).replace("|", "\\|").replace("\n", " "))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    _table(
        ("people", "personas_clave"), "People",
        [("name", "nombre", "Name"), ("context", "contexto", "Context")],
    )
    _table(
        ("dates", "fechas"), "Dates",
        [
            ("date", "fecha", "Date"),
            ("date_normalized", "fecha_normalizada", "Normalized"),
            ("context", "contexto", "Context"),
        ],
    )
    _table(
        ("legal_references", "referencias_legales"), "Legal References",
        [("name", "nombre", "Name"), ("context", "contexto", "Context")],
    )
    _table(
        ("rivers", "rios"), "Rivers",
        [
            ("name", "nombre", "Name"),
            ("alternative_spellings", "ortografias_alternativas", "Alternative Spellings"),
            ("context", "contexto", "Context"),
        ],
    )
    _table(
        ("events", "eventos_clave"), "Events",
        [("event", "evento", "Event"), ("context", "contexto", "Context")],
    )
    _table(
        ("mines", "minas"), "Mines",
        [("name", "nombre", "Name"), ("context", "contexto", "Context")],
    )
    _table(
        ("properties", "propiedades"), "Properties",
        [("name", "nombre", "Name"), ("context", "contexto", "Context")],
    )

    return "\n".join(lines).strip()


_CONTAINER_DOC_TYPES = {DocType.folder, DocType.group}


def _resolve_container_doc(
    selected_doc_ids: list[str], library_path: str
) -> Document | None:
    """Determine which document should receive catalogue output.

    The write target follows the selected document hierarchy, not the
    enclosing folder:
    - a selected folder/group stays on that folder/group
    - a selected PDF/file stays on itself
    - selected page children resolve to their parent PDF
    - multi-page or mixed selections resolve to the selected parent doc
      when one of the selected docs is the direct parent of the others

    Returns None only when the selection cannot be resolved to any real
    document in the library.
    """
    if not selected_doc_ids or not library_path:
        return None

    db = db_manager.get_database(library_path)
    docs = [db.get(Document, did) for did in selected_doc_ids]
    docs = [d for d in docs if d is not None]
    if not docs:
        return None

    if len(docs) == 1:
        doc = docs[0]
        if doc.doc_type == DocType.page and doc.parent_id:
            parent = db.get(Document, doc.parent_id)
            if parent is not None:
                return parent
        return doc

    folders = [d for d in docs if d.doc_type in _CONTAINER_DOC_TYPES]
    if len(folders) == 1:
        return folders[0]

    direct_parent_docs = [
        d for d in docs
        if d.id in {child.parent_id for child in docs if child.parent_id}
    ]
    if len(direct_parent_docs) == 1:
        return direct_parent_docs[0]

    parent_ids = {d.parent_id for d in docs if d.parent_id}
    if len(parent_ids) == 1:
        parent_id = next(iter(parent_ids))
        parent = db.get(Document, parent_id)
        if parent and parent.doc_type in _CONTAINER_DOC_TYPES:
            return parent
        if parent is not None:
            return parent

    # Fallback: first folder in selection when present.
    if folders:
        return folders[0]

    # Last resort: the first resolved document. This keeps mixed file
    # selections from dropping their output on the floor.
    return docs[0]


def _group_documents_by_case(
    container: Document, library_path: str
) -> dict[str | None, list[Document]]:
    """Group documents under container by case_id (#1096).

    Returns dict mapping case_id -> list of docs with that case_id.
    Docs with None/empty case_id are grouped under None key.
    """
    if not library_path or container.doc_type not in (DocType.folder, DocType.group):
        return {None: [container]}

    db = db_manager.get_database(library_path)
    try:
        # Query all children of this container
        all_docs = db.query(Document, parent_id=container.id) or []
        groups: dict[str | None, list[Document]] = {}
        for doc in all_docs:
            case = doc.case_id or None
            if case not in groups:
                groups[case] = []
            groups[case].append(doc)
        return groups if groups else {None: [container]}
    except Exception as exc:
        logger.warning(f"Case grouping query failed: {exc}; using container only")
        return {None: [container]}


def _grouping_is_ambiguous(
    groups: dict[str | None, list[Document]],
    min_items: int = 25,
) -> bool:
    """Heuristic used by #1097: many mixed docs with unassigned case_id."""
    docs = [doc for members in groups.values() for doc in members]
    if len(docs) < min_items:
        return False
    has_unassigned = None in groups
    file_types = {
        str(getattr(doc, "file_type", ""))
        for doc in docs
        if getattr(doc, "file_type", None)
    }
    mixed_types = len(file_types) > 1
    return has_unassigned and mixed_types


def _proposed_groupings(groups: dict[str | None, list[Document]]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for case_id, members in groups.items():
        proposals.append(
            {
                "case_id": case_id,
                "count": len(members),
                "document_ids": [doc.id for doc in members],
                "document_names": [doc.name for doc in members[:10]],
            }
        )
    proposals.sort(key=lambda row: row["count"], reverse=True)
    return proposals


def _resolve_write_target(
    selected_doc_ids: list[str], library_path: str
) -> Document | None:
    """Where to attach catalogue / KG writes.

    Prefers the hierarchy-aware document target resolved by
    `_resolve_container_doc()`. That means folders stay on folders,
    single PDFs/files stay on themselves, and page children resolve to
    their parent PDF. If nothing resolves, fall back to the selected
    document(s) so one-file selections still keep their output.

    Returns None only when neither a container nor any valid selected
    document can be loaded — callers should warn-and-skip in that case.
    """
    container = _resolve_container_doc(selected_doc_ids, library_path)
    if container is not None:
        return container
    if not selected_doc_ids or not library_path:
        return None
    db = db_manager.get_database(library_path)
    docs = [db.get(Document, did) for did in selected_doc_ids]
    docs = [d for d in docs if d is not None]
    return docs[0] if docs else None


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="catalogue",
    display_name="Archival Summary",
    description="Compose nine-section archival summary for a folder (leaf node of the Catalogue workflow)",
    category="llm",
    icon="books.vertical",
    color="brown",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=CATALOGUE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, CATALOGUE_CONFIG),
    default_prompt=_build_prompt("Spanish"),
    prompt_builder=build_catalogue_prompt,
    sort_order=9,
)
async def catalogue(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate nine-section catalogue for the container of processed files.

    Two execution paths:
    1. **Composable workflow** (per-section extractors already ran): the
       container has KnowledgeClaim/KnowledgeEntity rows. Build the
       9-section data from those rows and synthesize only the resumen
       narrative via a small LLM call (#727).
    2. **Monolithic workflow** (Transcribe → Catalogue, no extractors):
       no claims exist. Fall back to a single full-extraction LLM call
       that fills every section.
    """
    text = inputs.get("text", "")
    # Catalogue only declares one wired input now (`data` from
    # merge_extracts). When `text` isn't on the input port, pull the
    # transcript out of state.outputs so the node fires once — when
    # `data` is ready — instead of twice (once on the `text` edge alone,
    # once on the `data` edge). Multi-input LangGraph nodes fire whenever
    # any input is ready (#837 follow-up).
    if not text:
        for node_output in (state.get("outputs") or {}).values():
            if not isinstance(node_output, dict):
                continue
            candidate = node_output.get("text")
            # Discriminate transcribe-aggregator output from extractor or
            # cleanup output: only the parallel-aggregator wrapper carries
            # both `text` and a list under `texts`.
            if (
                isinstance(candidate, str)
                and candidate
                and isinstance(node_output.get("texts"), list)
            ):
                text = candidate
                break

    # Resolve language via auto-detect when the user picked "auto" (or
    # left it blank). Concrete names like "English" / "Spanish" bypass
    # detection. See fichero/lang_detect.py for the detector.
    from fichero.lang_detect import resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"), text, default="English"
    )
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    # Prefer a folder/group container, but fall back to the selected
    # document(s) so single-file selections still get a catalogue saved
    # on the file itself (#1087). Variable name kept as `container` for
    # diff-friendliness — semantically it's the write target now.
    container = _resolve_write_target(selected_doc_ids, library_path)

    # Short-circuit before the (~5s) LLM work when there's nowhere to
    # write the result — without a target we'd discard the narrative
    # immediately after generating it (#1087). The "no container
    # resolved" warning still fires below so the user sees why nothing
    # was saved.
    if not container or not library_path:
        logger.warning(
            "Catalogue: no write target resolved (selected_doc_ids=%s); "
            "skipping LLM call and artifact save",
            selected_doc_ids,
        )
        return {
            "text": "",
            "value": None,
            "error": (
                "Catalogue: no write target resolved from selection — "
                "no artifact saved."
            ),
        }

    # Optional human-in-the-loop pause for ambiguous grouping proposals (#1097).
    if inputs.get("hitl_on_ambiguous_grouping", False):
        groups = _group_documents_by_case(container, library_path)
        min_items = int(inputs.get("ambiguous_min_items", 25) or 25)
        if _grouping_is_ambiguous(groups, min_items=min_items):
            # Typed human-in-the-loop contract (#2529) — one Pydantic payload
            # shared with any future "Ask / Human Review" node, instead of an
            # ad-hoc dict the frontend has to parse blind.
            from fichero.workflows.human_review import ask_human

            ask_human(
                question=(
                    "Catalogue grouping appears ambiguous. Confirm, split, "
                    "or merge groups, then resume."
                ),
                kind="catalogue_grouping_confirmation",
                context={
                    "container_id": container.id,
                    "container_name": container.name,
                    "proposed_groupings": _proposed_groupings(groups),
                },
            )

    # Bubbleable LLM-error messages from any of the catalogue's nested
    # chat() calls. Surfaced in the result["error"] when nothing got
    # produced — quota / auth / rate-limit are user-actionable and
    # should appear in Activity, not be swallowed (Daniel: "we need
    # to do better error checking — alert or something").
    catalogue_errors: list[str] = []

    # --- Path 1: claims already exist for this container -------------------
    # If extractors ran ahead of catalogue (composable workflow), use the
    # rows they wrote as additional context for the narrative paragraph.
    # Note: data dict is no longer used to render structured markdown
    # (per Daniel's "we don't need anything in the text" — body is just
    # the paragraph). It's used only to surface entities to the LLM.
    data: dict[str, Any] | None = None
    # Track whether KG data (entities/claims) already exists from extract_all.
    # When True, a narrative-only failure is a partial success (KG data
    # landed) and should be reported as a warning, not a hard abort (#1169).
    has_kg_data: bool = False
    if container and library_path:
        try:
            data = _build_data_from_claims(container.id, library_path)
        except Exception as exc:
            logger.warning(f"Catalogue: claim read failed ({exc}); falling through")
            data = None
        if data is not None:
            has_kg_data = True
            claim_context = _format_claims_as_context(
                data, cap_overrides=inputs.get("claim_context_caps"),
            )
            paragraph, chunk_summaries = await _generate_resumen(
                text, output_language, llm_config,
                claim_context=claim_context, error_sink=catalogue_errors,
            )
            data["summary"] = paragraph
            data["chunk_summaries"] = chunk_summaries
            logger.info(
                f"Catalogue: built from existing claims on {container.id} "
                f"({len(claim_context)} chars of entity context)"
            )

    # --- Path 2: fallback — no claims yet, generate from raw transcripts ----
    if data is None:
        if not text:
            logger.warning("Catalogue: no text input; nothing to catalogue")
            return {
                "text": "",
                "value": None,
                "error": "No aggregated text provided to catalogue tool",
            }

        logger.info(f"Catalogue: Path 2 (no claims) running on {len(text)} chars in {output_language}")
        # Reuse the chunked _generate_resumen — same map-reduce path used
        # by Path 1 when claims exist. Without entity context, the LLM
        # works from raw transcripts only, but still survives Apple
        # Intelligence's small context window via chunking.
        # Pass error_sink so any LLM failure surfaces as result["error"]
        # rather than silently producing an empty narrative + no
        # artifact. (#1011)
        try:
            paragraph, chunk_summaries = await _generate_resumen(
                text, output_language, llm_config, claim_context="",
                error_sink=catalogue_errors,
            )
        except Exception as exc:
            logger.error(f"Catalogue LLM call failed: {exc}")
            return {"text": "", "value": None, "error": str(exc)}
        response = paragraph
        data = {"chunk_summaries": chunk_summaries}

        # Prompt asks for markdown directly (no JSON intermediary). Strip
        # any stray code fences just in case the model wrapped the output.
        raw = response.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        # Use the markdown response as-is. data stays None — per-section
        # typed entity artifacts are produced by the separate Extract
        # People / Extract Dates / etc. nodes in the composable workflow.
        markdown = raw
    else:
        # Path 1 (claims-derived): use only the LLM-generated paragraph
        # stored under data["summary"] as the catalogue body. The full
        # 9-section markdown render is no longer used — Daniel: "we don't
        # need anything in the text, it's already in the catalogue section".
        # Per-entity data lives in the typed entity artifacts (which
        # KnowledgeGraph tab renders) so duplicating it here is noise.
        markdown = (data.get("summary", "") if data else "") or ""

    # Multi-output catalogue (Phase E, #805): produce THREE artifacts —
    # narrative, timeline, keywords — each from a focused LLM call.
    # Small models follow short prompts more reliably than one big prompt
    # asking for everything. Idempotent: prior catalogue.* artifacts on
    # this container are deleted before saving new ones, so reruns don't
    # accumulate (Daniel: "I see multiple Catalogue entries").
    saved_artifact_ids: list[str] = []
    if container and library_path and markdown:
        try:
            db = db_manager.get_database(library_path)
            provider = getattr(llm_config, "provider", None)
            model = getattr(llm_config, "model", None)
            run_id = state.get("task_id")

            # Timeline is rendered programmatically from claim-derived
            # dates — no LLM call needed (small models hallucinate dates,
            # large models don't add value over a deterministic sort).
            # Keywords still goes through the LLM (subject synthesis is
            # genuinely a writing task).
            claim_context = _format_claims_as_context(
                data, cap_overrides=inputs.get("claim_context_caps"),
            ) if data else ""
            timeline_md = _generate_timeline(data)
            keywords_md = await _generate_keywords(
                text, output_language, llm_config, claim_context,
                error_sink=catalogue_errors,
            )

            # Delete prior catalogue.* artifacts so reruns overwrite, not
            # accumulate. Keep legacy 'catalogue' (no-suffix) deletions too
            # so existing libraries stop showing both old and new on rerun.
            from fichero.models import Artifact as ArtifactModel
            try:
                prior = list(db.query(ArtifactModel, document_id=container.id))
                for a in prior:
                    at = a.artifact_type or ""
                    if at == "catalogue" or at.startswith("catalogue."):
                        try:
                            db.delete(a)
                        except Exception as ex:
                            logger.warning(f"Catalogue: prior artifact delete failed ({ex})")
            except Exception as ex:
                logger.warning(f"Catalogue: prior artifact query failed ({ex})")

            # Per-chunk summaries as separate artifacts (#840)
            chunk_summaries = data.get("chunk_summaries", []) if data else []
            for chunk_index, chunk_text in enumerate(chunk_summaries, 1):
                if not chunk_text:
                    continue
                a = Artifact(
                    document_id=container.id,
                    artifact_type=f"catalogue.chunk.{chunk_index}",
                    content=chunk_text,
                    data=None,
                    provider=provider,
                    model=model,
                    run_id=run_id,
                )
                db.save(a)
                saved_artifact_ids.append(a.id)

            # Three new artifacts.
            artifacts_to_save = [
                ("catalogue.narrative", markdown),
                ("catalogue.timeline", timeline_md),
                ("catalogue.keywords", keywords_md),
            ]
            for atype, content in artifacts_to_save:
                if not content:
                    continue
                a = Artifact(
                    document_id=container.id,
                    artifact_type=atype,
                    content=content,
                    data=data if atype == "catalogue.narrative" else None,
                    provider=provider,
                    model=model,
                    run_id=run_id,
                )
                db.save(a)
                saved_artifact_ids.append(a.id)

            # Folder's page_content shows the narrative (the headline)
            container.page_content = markdown
            container.updated_at = datetime.now()
            db.save(container)

            logger.info(
                f"Catalogue: saved {len(saved_artifact_ids)} artifacts on container "
                f"{container.id} ({container.name}); updated page_content"
            )
            if saved_artifact_ids:
                emit_workflow_artifact_changes(
                    str(db.path.parent),
                    artifact_ids=saved_artifact_ids,
                    document_ids=[container.id],
                )
        except Exception as exc:
            logger.error(f"Catalogue: failed to save artifacts: {exc}")

    result: dict[str, Any] = {
        "text": markdown,
        "value": data,
        "results": [{"data": data, "markdown": markdown}],
        "artifacts": saved_artifact_ids,
        "container_id": container.id if container else None,
    }
    # Surface upstream LLM failures (quota / auth / rate-limit / model
    # down) so Activity / inspector can show an alert instead of a
    # silent empty narrative. Pick the most actionable message.
    #
    # #1169: When KG data already exists from extract_all (has_kg_data),
    # a narrative-only failure is partial success — abort signal ("error")
    # would roll back a successful extraction run. Use "warning" instead
    # so the workflow completes with KG data intact.
    if not markdown and catalogue_errors:
        actionable = next(
            (e for e in catalogue_errors
             if any(k in e.lower() for k in ("quota", "limit", "401", "403", "402"))),
            catalogue_errors[0],
        )
        msg = (
            f"Catalogue: {len(catalogue_errors)} LLM call(s) failed — "
            f"{actionable}"
        )
        if has_kg_data:
            result["warning"] = msg + " (KG extraction data was written successfully)"
            logger.warning("catalogue: narrative failed but KG data exists — partial success: %s", actionable)
        else:
            result["error"] = msg
    elif not markdown and not saved_artifact_ids:
        # #1011: catch the "ran successfully but produced nothing"
        # case. Without an explicit error, the workflow appears to
        # succeed but the inspector finds no catalogue artifact —
        # the most confusing failure mode.
        if has_kg_data:
            result["warning"] = (
                "Catalogue: narrative was not generated. "
                "KG extraction data is available — retry to add narrative."
            )
        else:
            result["error"] = (
                "Catalogue: LLM produced no narrative — no catalogue "
                "artifact was saved. Check provider/model availability "
                "and retry."
            )

    # Auto-refresh derived KG stores after a successful catalogue run
    # (#899). Writes <library>/kg.nt and ensures every entity has its
    # LanceDB vector. Cheap on small libraries (~100ms / 1k entities);
    # capped at 60s to avoid blocking workflow completion on huge
    # corpora. Failures log + carry on — kg.nt being stale isn't
    # worth taking down a successful catalogue.
    if library_path and saved_artifact_ids:
        try:
            from fichero.kg.rebuild import rebuild_kg

            db = db_manager.get_database(library_path)
            stats = rebuild_kg(db, vectors=False, triples=True)
            logger.info(
                "catalogue: auto-rebuilt kg.nt — %d entities, %d claims, "
                "%d triples written",
                stats["entities"], stats["claims"], stats["triples_written"],
            )
        except Exception as exc:
            logger.warning("catalogue: kg.nt auto-rebuild failed: %s", exc)

    return result


# =============================================================================
# Per-section artifact extraction
# =============================================================================

# (input_key, artifact_type, field_order_for_rendering). Field order puts the
# most identifying field first so the inspector's list view can render
# "primary — detail — detail" rows.
_TABLE_SECTIONS: list[tuple[str, str, list[str]]] = [
    ("people", "people", ["name", "context"]),
    ("dates", "dates", ["date_normalized", "date", "context"]),
    ("legal_references", "legal_references", ["name", "context"]),
    ("rivers", "rivers", ["name", "alternative_spellings", "context"]),
    ("events", "events", ["event", "context"]),
    ("mines", "mines", ["name", "context"]),
    ("properties", "properties", ["name", "context"]),
]


def _iter_section_artifacts(data: dict[str, Any]):
    """Yield (artifact_type, {content, data}) for each populated section.

    Each section becomes its own artifact so researchers can browse them
    independently in the inspector — e.g. a "rivers" artifact with a clean
    list of rivers, not buried inside a JSON catalogue blob.
    """
    # Narrative summary as its own artifact.
    summary = data.get("summary") or data.get("resumen")
    if summary:
        yield "summary", {"content": str(summary), "data": None}

    # Keywords as a semicolon-joined string + original list in data.
    keywords = data.get("keywords") or data.get("palabras_clave")
    if keywords:
        if isinstance(keywords, list):
            content = "; ".join(str(k) for k in keywords)
            payload = {"keywords": keywords}
        else:
            content = str(keywords)
            payload = {"keywords": [str(keywords)]}
        yield "keywords", {"content": content, "data": payload}

    # Table-shaped sections: each row rendered as one line, full rows in data.
    # Legacy artifacts may still carry Spanish keys; fall back to those.
    _LEGACY_SECTION_KEY = {
        "people": "personas_clave", "dates": "fechas",
        "legal_references": "referencias_legales", "rivers": "rios",
        "events": "eventos_clave", "mines": "minas",
        "properties": "propiedades",
    }
    for src_key, artifact_type, preferred_order in _TABLE_SECTIONS:
        items = data.get(src_key) or data.get(_LEGACY_SECTION_KEY.get(src_key, "")) or []
        if not items:
            continue

        # Readable content: one line per item, primary field first.
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                lines.append(str(item))
                continue
            primary = (
                item.get(preferred_order[0])
                or item.get("name") or item.get("event")
                or item.get("nombre") or item.get("evento")
            )
            if not primary:
                continue
            extras: list[str] = []
            for field in preferred_order[1:]:
                val = item.get(field)
                if not val:
                    continue
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                extras.append(str(val))
            if extras:
                lines.append(f"{primary} — {' — '.join(extras)}")
            else:
                lines.append(str(primary))

        yield artifact_type, {"content": "\n".join(lines), "data": {"items": items}}


# =============================================================================
# Phase 6 — build catalogue data from existing KG claims (#727)
# =============================================================================


def _build_data_from_claims(
    container_id: str,
    library_path: str,
) -> dict[str, Any] | None:
    """Build the 9-section catalogue data dict from existing KG rows.

    Returns ``None`` when no claims exist for the container (callers fall
    back to the original full-extraction LLM path).

    The 9-section schema after the generification (#726):
    - people           ← KnowledgeEntity(person)  + claim
    - places           ← KnowledgeEntity(location) + claim    (NEW)
    - organizations    ← KnowledgeEntity(organization)+ claim (NEW)
    - events           ← KnowledgeEntity(event)    + claim
    - keywords         ← KnowledgeEntity(concept)  + claim
    - dates            ← KnowledgeClaim with no entity_ids (date-style)
    - summary          ← filled by the caller via a small LLM call

    Archive-specific sections (rivers/mines/properties/legal_references)
    were dropped from defaults but old archived data may still have the
    matching artifact_types — those keep their markdown previews; we
    don't try to reconstruct them from the KG.
    """
    from fichero.knowledge_models import (
        EntityType,
        KnowledgeClaim,
        KnowledgeEntity,
    )
    from fichero.models import Document

    db = db_manager.get_database(library_path)
    # Query claims for the container AND all descendant page docs.
    # Per-page entity storage (0.0.2): extractors now write claims to
    # PAGE doc_ids rather than the container. Without expanding the
    # query to descendants, catalogue would see zero claims and fall
    # to Path 2 (text-only synthesis) on every run.
    container_descendants = list(db.query(Document, parent_id=container_id))
    descendant_ids = [d.id for d in container_descendants]
    all_doc_ids = [container_id] + descendant_ids
    claims = []
    for doc_id in all_doc_ids:
        claims.extend(db.query(KnowledgeClaim, source_document_id=doc_id))
    if not claims:
        return None

    # Cache entities by id so we don't re-query for each claim.
    entity_ids = {eid for c in claims for eid in (c.entity_ids or [])}
    entities_by_id: dict[str, KnowledgeEntity] = {}
    for eid in entity_ids:
        try:
            ent = db.get(KnowledgeEntity, eid)
            if ent:
                entities_by_id[ent.id] = ent
        except Exception:
            continue

    # Group claims by entity type (or "date" bucket for entity-less claims).
    type_to_section = {
        EntityType.person: "people",
        EntityType.location: "places",
        EntityType.organization: "organizations",
        EntityType.event: "events",
        EntityType.concept: "keywords",
    }
    data: dict[str, Any] = {
        "people": [],
        "places": [],
        "organizations": [],
        "events": [],
        "keywords": [],
        "dates": [],
    }
    seen_canonical_per_section: dict[str, set[str]] = {k: set() for k in data}

    for claim in claims:
        entity_id = (claim.entity_ids or [None])[0]
        entity = entities_by_id.get(entity_id) if entity_id else None

        if entity is None:
            # Date-style claim: no entity, normalized date in metadata.
            md = claim.metadata or {}
            fecha = md.get("date_text") or claim.text or ""
            normalized = md.get("date_normalized") or ""
            data["dates"].append({
                "date": fecha,
                "date_normalized": normalized,
                "context": claim.source_excerpt or "",
            })
            continue

        section_key = type_to_section.get(entity.entity_type)
        if not section_key:
            continue

        # Dedup by canonical name within a section so multiple claims
        # for the same entity (e.g. across runs) collapse to one row.
        seen = seen_canonical_per_section[section_key]
        if entity.canonical_name in seen:
            continue
        seen.add(entity.canonical_name)

        if section_key == "keywords":
            # Keywords render as a flat list of strings, not objects.
            data[section_key].append(entity.canonical_name)
        elif section_key == "events":
            data[section_key].append({
                "event": entity.canonical_name,
                "context": claim.source_excerpt or entity.description or "",
            })
        else:
            data[section_key].append({
                "name": entity.canonical_name,
                "alternative_spellings": list(entity.aliases or []),
                "context": claim.source_excerpt or entity.description or "",
            })

    return data


# Default per-section caps for the claim_context dump fed to the
# catalogue narrative LLM. Folders with hundreds of entities (e.g.
# acknowledgments pages with 100+ contributors) produced 25K+ char
# prompts that hung OpenRouter routing — both qwen3.5 and
# claude-sonnet-4.6 timed out at 300s on the same prompt. Defaults
# below were tuned to keep the context block under ~5K chars even on
# dense folders. Per-workflow override via node config:
#
#   "claim_context_caps": {
#     "people": 50, "events": 5, ...
#   }
#
# Defaults preserved when caps dict is missing or partial — only the
# keys present in the override change. (#865)
_DEFAULT_CTX_CAPS: dict[str, int] = {
    "people": 30,
    "places": 20,
    "organizations": 15,
    "events": 15,  # events have full sentences — heaviest by char
    "dates": 30,
    "keywords": 30,
}


def _resolve_ctx_caps(overrides: dict[str, Any] | None) -> dict[str, int]:
    """Merge per-workflow cap overrides with the defaults. Non-int
    values (typo'd config) are dropped silently — the cap stays at
    default rather than crashing the catalogue narrative call."""
    caps = dict(_DEFAULT_CTX_CAPS)
    if not overrides:
        return caps
    for key, val in overrides.items():
        if key in caps and isinstance(val, int) and val > 0:
            caps[key] = val
    return caps


def _format_claims_as_context(
    data: dict[str, Any] | None,
    cap_overrides: dict[str, Any] | None = None,
) -> str:
    """Render the claim-derived dict as inline context lines for the
    catalogue prompt. The Extract* nodes already wrote KnowledgeClaim
    rows; this surfaces them to the LLM so its narrative paragraph is
    informed by typed entities (not just the raw transcripts).
    Daniel: 'catalogue should take the output of all the previous ones
    and add it together'.

    Per-section caps (resolved from defaults + workflow-config
    overrides) prevent dense folders from producing oversized prompts.
    Each section is truncated to its cap; overflow is surfaced as a
    single '(... +N more)' line so the LLM knows the list isn't
    exhaustive. (#865)
    """
    if not data:
        return ""
    caps = _resolve_ctx_caps(cap_overrides)
    lines: list[str] = []

    def _name_of(item: Any) -> str:
        if isinstance(item, dict):
            return item.get("name") or item.get("nombre") or ""
        return str(item)

    def _event_of(item: Any) -> str:
        if isinstance(item, dict):
            return item.get("event") or item.get("evento") or ""
        return str(item)

    def _capped_join(items: list[str], cap: int, sep: str = ", ") -> str:
        """Join at most `cap` items; append '(... +N more)' when truncated."""
        if len(items) <= cap:
            return sep.join(items)
        return sep.join(items[:cap]) + f"{sep}(… +{len(items) - cap} more)"

    if people := (data.get("people") or data.get("personas_clave")):
        names = [n for n in (_name_of(p) for p in people) if n]
        if names:
            lines.append(f"People found: {_capped_join(names, caps['people'])}")
    if places := (data.get("places") or data.get("lugares")):
        names = [n for n in (_name_of(p) for p in places) if n]
        if names:
            lines.append(f"Places found: {_capped_join(names, caps['places'])}")
    if orgs := (data.get("organizations") or data.get("organizaciones")):
        names = [n for n in (_name_of(o) for o in orgs) if n]
        if names:
            lines.append(
                f"Organizations found: {_capped_join(names, caps['organizations'])}"
            )
    if events := (data.get("events") or data.get("eventos_clave")):
        descs = [d for d in (_event_of(e) for e in events) if d]
        if descs:
            capped = descs[:caps['events']]
            extra = len(descs) - len(capped)
            block = "Events found:\n  - " + "\n  - ".join(capped)
            if extra > 0:
                block += f"\n  - (… +{extra} more)"
            lines.append(block)
    if dates := (data.get("dates") or data.get("fechas")):
        bits = []
        for d in dates:
            if isinstance(d, dict):
                f = (
                    d.get("date_normalized") or d.get("date")
                    or d.get("fecha_normalizada") or d.get("fecha") or ""
                )
                if f:
                    bits.append(f)
        if bits:
            lines.append(f"Dates found: {_capped_join(bits, caps['dates'])}")
    if keywords := (data.get("keywords") or data.get("palabras_clave")):
        kws = [str(k) for k in keywords if k]
        if kws:
            lines.append(
                f"Keywords: {_capped_join(kws, caps['keywords'], sep='; ')}"
            )
    return "\n".join(lines)


# Per-call character budget for on-device models (Apple Intelligence ≈ 4K
# tokens, conservative ~12K chars). Cloud models tolerate much more but
# also benefit from focused chunks: shorter context = sharper summaries.
# Triggers map-reduce when transcripts exceed this size.
_RESUMEN_CHUNK_SIZE = 12000

# Providers whose flagship models comfortably hold an entire folder's
# transcripts in a single context window (~100K+ chars). For these we
# skip map-reduce entirely — feeding pre-summarised chunks to a frontier
# model produces visibly worse output than feeding the raw transcripts
# (#835 — per-chunk hallucinations get faithfully echoed by the
# synthesis pass). The chunked path stays correct as a fallback for
# Apple Intelligence + small local models.
_FRONTIER_PROVIDERS: frozenset[str] = frozenset({
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "azure",
    "vertex_ai",
    "bedrock",
})
_FRONTIER_CHUNK_SIZE = 100_000


def _effective_chunk_size(llm_config: LLMConfig) -> int:
    """Pick the chunk-threshold based on provider capability.
    Frontier cloud providers handle ~100K+ chars in one call; smaller
    on-device providers (Apple Intelligence, small Ollama models) need
    the conservative 12K cap. (#835)
    """
    provider = (getattr(llm_config, "provider", "") or "").lower()
    if provider in _FRONTIER_PROVIDERS:
        return _FRONTIER_CHUNK_SIZE
    return _RESUMEN_CHUNK_SIZE


_LEADING_TITLE_RE = re.compile(
    # Strip a leading title line at the start of the narrative — small models
    # add **Catalogue Entry** / "Catalogue Entry:" / "Summary:" headers
    # despite the prompt saying "no headers". (#828)
    r"^\s*(?:\*\*[^*\n]+\*\*|(?:Catalogue|Catálogo)\s+Entry\s*[:\-—]?|"
    r"(?:Summary|Resumen)\s*[:\-—]?|"
    r"#{1,6}\s+[^\n]+)\s*\n+",
    flags=re.IGNORECASE,
)


def _strip_narrative_header(text: str) -> str:
    """Strip a leading title/header line from a narrative paragraph.
    Catalogue narrative is supposed to be plain prose, but small models
    insist on prefixing **Catalogue Entry** / Summary: / etc. (#828)."""
    if not text:
        return text
    cleaned = _LEADING_TITLE_RE.sub("", text, count=1)
    return cleaned.strip()


async def _generate_resumen(
    text: str,
    output_language: str,
    llm_config: LLMConfig,
    claim_context: str = "",
    error_sink: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Generate the catalogue narrative paragraph from the merged transcript
    plus optional typed-entity context surfaced from the Extract* nodes.

    Map-reduce when text exceeds _RESUMEN_CHUNK_SIZE (Apple Intelligence's
    on-device window can't hold 20K+ char transcripts). Each chunk produces
    a brief summary; a final synthesis pass combines them with the claim
    context into the catalogue narrative paragraph. Mirrors the legacy
    Generic_Catalogue.jsonl 'summary' step's chunked approach.

    When ``claim_context`` is provided (composable workflow path), the LLM
    has both the raw transcripts and a structured summary of the entities
    already extracted — produces a richer, more grounded paragraph than
    transcripts alone.

    Returns: (final_narrative_text, list_of_chunk_summaries)
    - final_narrative_text: empty string on failure
    - list_of_chunk_summaries: empty list if not chunked (single-shot path)

    Reasoning is enabled at "medium" effort on the synthesis call sites
    (single-shot + final reduce) — Claude Sonnet 4.6's extended thinking
    measurably improves narrative quality on grounded synthesis tasks
    (#859). The chunk-summary calls in the map step skip reasoning —
    those are mechanical and the latency/cost isn't worth it. Apple
    Intelligence and other providers without a reasoning surface
    silently ignore the field.
    """
    import dataclasses

    if not text and not claim_context:
        return "", []

    context_block = (
        f"\n\nExtracted entities (from prior workflow steps):\n{claim_context}\n"
        if claim_context else ""
    )

    # Reasoning ON only for synthesis (single-shot + final reduce).
    # Chunk summaries stay fast — mechanical 3-5 sentence digest.
    synthesis_config = dataclasses.replace(llm_config, reasoning_effort="medium")

    # Single-shot path — text fits comfortably in this model's context
    # window. System+user split (#815): rules go to Apple Intelligence's
    # Instructions channel where they're authoritative; source text is
    # the user prompt. Frontier providers get a 100K cap so a typical
    # folder-scale transcript runs in one call instead of fan-out (#835).
    chunk_threshold = _effective_chunk_size(llm_config)
    if len(text) <= chunk_threshold:
        instructions = (
            f"You are an expert archivist. Write a 150-300 word "
            f"narrative catalogue entry in {output_language} summarizing "
            f"the document the user supplies. Plain prose, no headers, "
            f"no bullets, no JSON. Ground the narrative in concrete "
            f"names, places, and dates from the entities below."
            f"{context_block}"
        )
        try:
            response = await chat_with_fallback(
                text,
                config=synthesis_config,
                system=instructions,
                permissive_guardrails=True,
            )
        except Exception as exc:
            logger.warning(f"Catalogue: resumen LLM call failed ({exc}); using empty")
            if error_sink is not None:
                error_sink.append(str(exc))
            return "", []
        return _strip_narrative_header(response), []

    # Map-reduce path — text exceeds context window. Split, summarise each
    # chunk briefly, then synthesise the final paragraph from the chunk
    # summaries + entity context. Same shape as the legacy 7-step pipeline's
    # 'summary' step.
    chunks = _split_text_into_chunks(text, chunk_threshold)
    logger.info(
        f"Catalogue: text {len(text)} chars > {chunk_threshold} budget — "
        f"map-reducing across {len(chunks)} chunks"
    )

    chunk_instructions = (
        f"You are an expert archivist. Summarize the section the user "
        f"supplies in 3-5 sentences in {output_language}. Focus on "
        f"concrete names, dates, places, and events. Plain prose, no "
        f"headers, no bullets."
    )
    chunk_summaries: list[str] = []
    for index, chunk in enumerate(chunks):
        try:
            chunk_text = await chat_with_fallback(
                f"Section {index + 1} of {len(chunks)}:\n{chunk}",
                config=llm_config,
                system=chunk_instructions,
                permissive_guardrails=True,
            )
            chunk_summaries.append(chunk_text.strip())
        except Exception as exc:
            logger.warning(
                f"Catalogue: chunk {index + 1}/{len(chunks)} summary failed ({exc})"
            )
            if error_sink is not None:
                error_sink.append(str(exc))

    if not chunk_summaries:
        return ""

    combined_summaries = "\n\n".join(
        f"Section {i + 1}: {s}" for i, s in enumerate(chunk_summaries)
    )
    final_instructions = (
        f"You are an expert archivist. Synthesize the section summaries "
        f"the user supplies into a single 150-300 word finding-aid "
        f"abstract in {output_language}. Pack with concrete facts: full "
        f"names, exact dates, places, organizations, events, outcomes. "
        f"Plain prose, no headers, no bullets, no JSON."
        f"{context_block}"
    )
    try:
        # Final synthesis: reasoning ON (#859 — same as single-shot above).
        response = await chat_with_fallback(
            combined_summaries,
            config=synthesis_config,
            system=final_instructions,
            permissive_guardrails=True,
        )
    except Exception as exc:
        logger.warning(f"Catalogue: final synthesis failed ({exc}); using empty")
        return "", chunk_summaries
    return _strip_narrative_header(response), chunk_summaries


def _generate_timeline(data: dict[str, Any] | None) -> str:
    """Render a chronological timeline as markdown — programmatically,
    no LLM call.

    The dates extractor already produces `date_normalized` in YYYY-MM-DD
    format (lexicographic sort == chronological sort). Asking an LLM to
    re-sort and re-format these is both wasteful (one LLM call we can
    skip) and unreliable (small models hallucinate or miss-order dates).
    Read straight from the claim-derived data and render. Returns empty
    string when no dates are available.
    """
    if not data:
        return ""
    dates = data.get("dates") or data.get("fechas") or []
    if not dates:
        return ""

    rows: list[tuple[str, str]] = []
    for item in dates:
        if not isinstance(item, dict):
            continue
        normalized = (
            item.get("date_normalized")
            or item.get("fecha_normalizada")
            or item.get("date")
            or item.get("fecha")
            or ""
        ).strip()
        if not normalized:
            continue
        context = (
            item.get("context") or item.get("contexto") or ""
        ).strip().replace("\n", " ")
        rows.append((normalized, context))

    if not rows:
        return ""

    # Lexicographic sort on YYYY-MM-DD strings is chronological. Partial
    # dates (YYYY, YYYY-MM, YYYY-MM-DD/YYYY-MM-DD ranges) sort sensibly
    # under string ordering for practical archive use.
    rows.sort(key=lambda r: r[0])

    # De-dup identical (date, context) pairs that may arise from running
    # the workflow twice on the same container.
    seen: set[tuple[str, str]] = set()
    bullets: list[str] = []
    for date, ctx in rows:
        key = (date, ctx)
        if key in seen:
            continue
        seen.add(key)
        bullets.append(f"* **{date}** — {ctx}" if ctx else f"* **{date}**")
    return "\n".join(bullets)


async def _generate_keywords(
    text: str,
    output_language: str,
    llm_config: LLMConfig,
    claim_context: str = "",
    error_sink: list[str] | None = None,
) -> str:
    """Generate collection-level subject keywords as a semicolon-joined list.

    Distinct from per-page keyword extraction (#keywords_extract) — this is
    the COLLECTION's headline subject keywords, not page-level concepts.
    Returns empty string on failure.
    """
    if not text and not claim_context:
        return ""
    context_block = (
        f"\n\nExtracted entities (from prior workflow steps):\n{claim_context}\n"
        if claim_context else ""
    )
    bounded = text[:_RESUMEN_CHUNK_SIZE] if text else ""
    instructions = (
        f"You are an expert archivist. Generate subject keywords for "
        f"the collection the user supplies in {output_language}. Capture "
        f"themes, subjects, regions, time periods, and concepts the "
        f"source actually discusses — no minimum count, no padding. "
        f"Return ONE line: keywords separated by semicolons. No "
        f"preamble, no markdown, no commentary."
        f"{context_block}"
    )
    try:
        response = await chat_with_fallback(
            bounded,
            config=llm_config,
            system=instructions,
            permissive_guardrails=True,
        )
    except Exception as exc:
        logger.warning(f"Catalogue: keywords LLM call failed ({exc}); using empty")
        if error_sink is not None:
            error_sink.append(str(exc))
        return ""
    return response.strip()


def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks of at most max_chars. Prefers splitting on
    page boundaries (\n\n---\n\n, the aggregate node's separator) so each
    chunk is a coherent semantic unit. Falls back to paragraph or character
    boundaries if pages are themselves too large.
    """
    if len(text) <= max_chars:
        return [text]

    # Try page boundaries first (legacy aggregate separator).
    pages = text.split("\n\n---\n\n")
    chunks: list[str] = []
    current = ""
    for page in pages:
        if len(current) + len(page) + 8 <= max_chars:
            current = page if not current else current + "\n\n---\n\n" + page
        else:
            if current:
                chunks.append(current)
            # If a single page exceeds the budget, fall back to paragraph
            # split for that page.
            if len(page) > max_chars:
                paragraphs = page.split("\n\n")
                sub = ""
                for p in paragraphs:
                    if len(sub) + len(p) + 2 <= max_chars:
                        sub = p if not sub else sub + "\n\n" + p
                    else:
                        if sub:
                            chunks.append(sub)
                        # Last resort — slice on character count.
                        if len(p) > max_chars:
                            for i in range(0, len(p), max_chars):
                                chunks.append(p[i:i + max_chars])
                            sub = ""
                        else:
                            sub = p
                if sub:
                    chunks.append(sub)
                current = ""
            else:
                current = page
    if current:
        chunks.append(current)
    return chunks
