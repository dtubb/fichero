"""
Catalogue Tool

Generates a structured archival catalogue entry for a folder of documents,
producing a rich nine-section output matching the reference format in the
Archivo Judicial de Medellín catalogue.docx exemplars.

Contract:
- Expects aggregated `text` input (from upstream Transcribe → implicit aggregate).
- Reads `state.selected_doc_ids` to determine the container (folder) on which
  to save the final artifact. If the selection is a single folder doc, save
  there. If it's a list of file docs sharing a parent, save on the parent.
- Produces one Artifact on the container doc with type="catalogue", containing:
    - content: markdown rendering of the nine sections (human-readable)
    - data:    parsed JSON matching the nine-section schema
"""

from __future__ import annotations

import json
import logging
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
from fichero.llm import LLMConfig, chat
from fichero.db import db_manager
from fichero.models import Document, DocType, Artifact

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
        "default": "Spanish",
        "description": "Output language for catalogue narrative fields",
        "x-group": "primary",
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
            description="Aggregated transcription text from upstream step",
        ),
        # Optional inputs from upstream Extract* nodes. The catalogue tool
        # already reads typed entities from the DB (Path 1 — KnowledgeClaim
        # rows), but these explicit input ports let users wire the NER
        # outputs into the catalogue node so the graph visibly shows the
        # data flow. Wired in default presets; ignored at runtime if the
        # claims path already hydrated the prompt context.
        PortDef(id="people", name="People", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted people entities"),
        PortDef(id="places", name="Places", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted place entities"),
        PortDef(id="organizations", name="Organizations", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted organization entities"),
        PortDef(id="dates", name="Dates", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted date entities"),
        PortDef(id="events", name="Events", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted event entities"),
        PortDef(id="keywords", name="Keywords", port_type="input",
                data_type=DataType.TEXT, required=False,
                description="Optional: extracted keyword entities"),
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
  "resumen": "string — narrative summary, 150-300 words in __LANG__",
  "palabras_clave": ["keyword1", "keyword2", "..."],
  "personas_clave": [
    {"nombre": "...", "contexto": "role and importance in __LANG__"}
  ],
  "fechas": [
    {"fecha": "as written", "fecha_normalizada": "YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD", "contexto": "..."}
  ],
  "referencias_legales": [
    {"nombre": "...", "contexto": "..."}
  ],
  "rios": [
    {"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}
  ],
  "eventos_clave": [
    {"evento": "...", "contexto": "..."}
  ],
  "minas": [
    {"nombre": "...", "contexto": "..."}
  ],
  "propiedades": [
    {"nombre": "...", "contexto": "..."}
  ]
}"""


def _build_prompt(output_language: str) -> str:
    """Build the catalogue prompt.

    Adapted directly from the legacy Generic_Catalogue pipeline's final
    `library_catalogue_entry` step (fichero_archive/.../Generic_Catalogue.jsonl).
    That pipeline used 7 sequential steps — extract people, places, dates,
    timeline, tags, summary, then synthesize the catalogue entry. Here we
    collapse the synthesis into one step that produces the markdown entry
    directly. Per-section typed entities (Dates / People / Events) are
    produced by separate Extract* nodes in the composable workflow —
    this tool's job is the catalogue *synthesis*, not the extraction.

    Output is markdown (no JSON intermediary) since Daniel's mental model
    is "just give me the catalogue entry, not a data structure to render".
    """
    return f"""You are writing a catalogue entry for an archival document or
collection. You receive the aggregated transcriptions (possibly across many
pages or files).

Focus on documenting WHAT IS IN THE DOCUMENTS, not analysis or interpretation.
Use ALL available information to write the most accurate entry possible.

Write ONE rich narrative paragraph in the style of an archival finding-aid
abstract. Pack it with concrete facts: full names of the principal actors,
exact dates, place names, organizations involved, the chain of events, and
the documented outcomes. Read like a scholar summarising the case file —
not generic ("the documents discuss legal matters") but specific ("on the
night of 23-24 August 1922 the dredge No. 1 of the Compañía Minera Chocó
Pacífico sank in the río Condoto near Bazán island, leading to a judicial
investigation that eventually..."). Aim for 150-300 words. Paragraph form
only. No headings, no bullet lists, no section labels — the artifact is
labeled "Catalogue" in the inspector chrome and per-entity data (People,
Places, Dates, Events) is produced by separate extractor nodes shown in
the Knowledge Graph tab, so duplicating that structure here would just be
two copies of the same data drifting out of sync.

Rules:
- Write in {output_language}.
- Only include facts supported by the text. Do not speculate. Do not
  invent details.
- Preserve exact spelling of names, capitalize properly.
- Do not include your own analysis or commentary.

Return ONLY the paragraph. No surrounding prose, no headings, no code
fences."""


def build_catalogue_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    output_language = config.get("output_language", "Spanish")
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

    if resumen := data.get("resumen"):
        lines.append("## Resumen\n")
        lines.append(str(resumen))
        lines.append("")

    if keywords := data.get("palabras_clave"):
        lines.append("## Palabras Clave\n")
        if isinstance(keywords, list):
            lines.append("; ".join(str(k) for k in keywords))
        else:
            lines.append(str(keywords))
        lines.append("")

    def _table(section_key: str, title: str, columns: list[tuple[str, str]]) -> None:
        items = data.get(section_key) or []
        if not items:
            return
        lines.append(f"## {title}\n")
        lines.append("| " + " | ".join(c[1] for c in columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for item in items:
            if not isinstance(item, dict):
                continue
            row = []
            for key, _ in columns:
                val = item.get(key, "")
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                row.append(str(val).replace("|", "\\|").replace("\n", " "))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    _table("personas_clave", "Personas Clave", [("nombre", "Nombre"), ("contexto", "Contexto")])
    _table(
        "fechas",
        "Fechas",
        [("fecha", "Fecha"), ("fecha_normalizada", "Fecha Normalizada"), ("contexto", "Contexto")],
    )
    _table(
        "referencias_legales",
        "Referencias Legales",
        [("nombre", "Nombre"), ("contexto", "Contexto")],
    )
    _table(
        "rios",
        "Ríos",
        [
            ("nombre", "Nombre"),
            ("ortografias_alternativas", "Ortografías Alternativas"),
            ("contexto", "Contexto"),
        ],
    )
    _table("eventos_clave", "Eventos Clave", [("evento", "Evento"), ("contexto", "Contexto")])
    _table("minas", "Minas", [("nombre", "Nombre"), ("contexto", "Contexto")])
    _table("propiedades", "Propiedades", [("nombre", "Nombre"), ("contexto", "Contexto")])

    return "\n".join(lines).strip()


_CONTAINER_DOC_TYPES = {DocType.folder, DocType.group}


def _resolve_container_doc(
    selected_doc_ids: list[str], library_path: str
) -> Document | None:
    """Determine which document should receive the catalogue artifact.

    Priority:
    1. If exactly one doc is a folder/group, use it.
    2. If all selected docs share a common parent, and the parent is a
       folder/group, use that parent.
    3. If any selected doc is a folder/group, use the first such one.

    Returns None rather than a file document — catalogue artifacts only
    belong on containers (folders / groups), never on individual files.
    Callers should warn and skip when this happens.
    """
    if not selected_doc_ids or not library_path:
        return None

    db = db_manager.get_database(library_path)
    docs = [db.get(Document, did) for did in selected_doc_ids]
    docs = [d for d in docs if d is not None]
    if not docs:
        return None

    folders = [d for d in docs if d.doc_type in _CONTAINER_DOC_TYPES]
    if len(folders) == 1:
        return folders[0]

    parent_ids = {d.parent_id for d in docs if d.parent_id}
    if len(parent_ids) == 1:
        parent_id = next(iter(parent_ids))
        parent = db.get(Document, parent_id)
        if parent and parent.doc_type in _CONTAINER_DOC_TYPES:
            return parent

    # Fallback: first folder in selection.
    if folders:
        return folders[0]

    # No container anywhere in the selection or its parents — nothing to save on.
    return None


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="catalogue",
    display_name="Catalogue",
    description="Generate nine-section archival catalogue entry for a folder",
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
    output_language = inputs.get("output_language", "Spanish")
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_container_doc(selected_doc_ids, library_path)

    # --- Path 1: claims already exist for this container -------------------
    # If extractors ran ahead of catalogue (composable workflow), use the
    # rows they wrote as additional context for the narrative paragraph.
    # Note: data dict is no longer used to render structured markdown
    # (per Daniel's "we don't need anything in the text" — body is just
    # the paragraph). It's used only to surface entities to the LLM.
    data: dict[str, Any] | None = None
    if container and library_path:
        try:
            data = _build_data_from_claims(container.id, library_path)
        except Exception as exc:
            logger.warning(f"Catalogue: claim read failed ({exc}); falling through")
            data = None
        if data is not None:
            claim_context = _format_claims_as_context(data)
            paragraph = await _generate_resumen(
                text, output_language, llm_config, claim_context=claim_context
            )
            data["resumen"] = paragraph
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
        try:
            paragraph = await _generate_resumen(
                text, output_language, llm_config, claim_context=""
            )
        except Exception as exc:
            logger.error(f"Catalogue LLM call failed: {exc}")
            return {"text": "", "value": None, "error": str(exc)}
        response = paragraph

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
        # stored under data["resumen"] as the catalogue body. The full
        # 9-section markdown render is no longer used — Daniel: "we don't
        # need anything in the text, it's already in the catalogue section".
        # Per-entity data lives in the typed entity artifacts (which
        # KnowledgeGraph tab renders) so duplicating it here is noise.
        markdown = (data.get("resumen", "") if data else "") or ""

    # Save artifacts on the container document. Each section gets its own
    # artifact for the inspector's per-type rendering, plus one combined
    # "catalogue" artifact holding the full markdown for export.
    saved_artifact_ids: list[str] = []
    # Save when we have markdown content, regardless of whether we have
    # parsed JSON data (the new direct-markdown prompt path has no data).
    if container and library_path and markdown:
        try:
            db = db_manager.get_database(library_path)
            provider = getattr(llm_config, "provider", None)
            model = getattr(llm_config, "model", None)
            run_id = state.get("task_id")

            # Per-section typed artifacts are NO longer written by the
            # catalogue tool — the Extract* nodes (people_extract,
            # places_extract, dates_extract, etc.) already wrote them
            # before catalogue ran. Saving them here too produced
            # duplicate artifacts that drifted out of sync with the
            # extractor outputs. (composable workflow refactor)

            # Combined catalogue artifact with the full markdown — always
            # save so the user sees the headline catalogue entry.
            combined = Artifact(
                document_id=container.id,
                artifact_type="catalogue",
                content=markdown,
                data=data,
                provider=provider,
                model=model,
                run_id=run_id,
            )
            db.save(combined)
            saved_artifact_ids.append(combined.id)

            # Also write the catalogue markdown into the container's
            # page_content so the folder's Content tab shows the catalogue
            # entry directly. The individual per-section artifacts stay
            # available under the Artifacts tab once its UI lands.
            container.page_content = markdown
            container.updated_at = datetime.now()
            db.save(container)

            logger.info(
                f"Catalogue: saved {len(saved_artifact_ids)} artifacts on container "
                f"{container.id} ({container.name}); updated page_content"
            )
        except Exception as exc:
            logger.error(f"Catalogue: failed to save artifacts: {exc}")
    elif not container:
        logger.warning(
            "Catalogue: no container doc resolved (selected_doc_ids=%s); artifacts not saved",
            selected_doc_ids,
        )

    return {
        "text": markdown,
        "value": data,
        "results": [{"data": data, "markdown": markdown}],
        "artifacts": saved_artifact_ids,
        "container_id": container.id if container else None,
    }


# =============================================================================
# Per-section artifact extraction
# =============================================================================

# (input_key, artifact_type, field_order_for_rendering). Field order puts the
# most identifying field first so the inspector's list view can render
# "primary — detail — detail" rows.
_TABLE_SECTIONS: list[tuple[str, str, list[str]]] = [
    ("personas_clave", "people", ["nombre", "contexto"]),
    ("fechas", "dates", ["fecha_normalizada", "fecha", "contexto"]),
    ("referencias_legales", "legal_references", ["nombre", "contexto"]),
    ("rios", "rivers", ["nombre", "ortografias_alternativas", "contexto"]),
    ("eventos_clave", "events", ["evento", "contexto"]),
    ("minas", "mines", ["nombre", "contexto"]),
    ("propiedades", "properties", ["nombre", "contexto"]),
]


def _iter_section_artifacts(data: dict[str, Any]):
    """Yield (artifact_type, {content, data}) for each populated section.

    Each section becomes its own artifact so researchers can browse them
    independently in the inspector — e.g. a "rivers" artifact with a clean
    list of rivers, not buried inside a JSON catalogue blob.
    """
    # Narrative resumen as its own artifact.
    if resumen := data.get("resumen"):
        yield "summary", {"content": str(resumen), "data": None}

    # Keywords as a semicolon-joined string + original list in data.
    if keywords := data.get("palabras_clave"):
        if isinstance(keywords, list):
            content = "; ".join(str(k) for k in keywords)
            payload = {"keywords": keywords}
        else:
            content = str(keywords)
            payload = {"keywords": [str(keywords)]}
        yield "keywords", {"content": content, "data": payload}

    # Table-shaped sections: each row rendered as one line, full rows in data.
    for src_key, artifact_type, preferred_order in _TABLE_SECTIONS:
        items = data.get(src_key) or []
        if not items:
            continue

        # Readable content: one line per item, primary field first.
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                lines.append(str(item))
                continue
            primary = item.get(preferred_order[0]) or item.get("nombre") or item.get("evento")
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
    - personas_clave  ← KnowledgeEntity(person)  + claim
    - lugares          ← KnowledgeEntity(location) + claim    (NEW)
    - organizaciones   ← KnowledgeEntity(organization)+ claim (NEW)
    - eventos_clave    ← KnowledgeEntity(event)    + claim
    - palabras_clave   ← KnowledgeEntity(concept)  + claim
    - fechas           ← KnowledgeClaim with no entity_ids (date-style)
    - resumen          ← filled by the caller via a small LLM call

    Archive-specific sections (rios/minas/propiedades/referencias_legales)
    were dropped from defaults but old archived data may still have the
    matching artifact_types — those keep their markdown previews; we
    don't try to reconstruct them from the KG.
    """
    from fichero.knowledge_models import (
        EntityType,
        KnowledgeClaim,
        KnowledgeEntity,
    )

    db = db_manager.get_database(library_path)
    claims = db.query(KnowledgeClaim, source_document_id=container_id)
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
        EntityType.person: "personas_clave",
        EntityType.location: "lugares",
        EntityType.organization: "organizaciones",
        EntityType.event: "eventos_clave",
        EntityType.concept: "palabras_clave",
    }
    data: dict[str, Any] = {
        "personas_clave": [],
        "lugares": [],
        "organizaciones": [],
        "eventos_clave": [],
        "palabras_clave": [],
        "fechas": [],
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
            data["fechas"].append({
                "fecha": fecha,
                "fecha_normalizada": normalized,
                "contexto": claim.source_excerpt or "",
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

        if section_key == "palabras_clave":
            # Keywords render as a flat list of strings, not objects.
            data[section_key].append(entity.canonical_name)
        elif section_key == "eventos_clave":
            data[section_key].append({
                "evento": entity.canonical_name,
                "contexto": claim.source_excerpt or entity.description or "",
            })
        else:
            data[section_key].append({
                "nombre": entity.canonical_name,
                "ortografias_alternativas": list(entity.aliases or []),
                "contexto": claim.source_excerpt or entity.description or "",
            })

    return data


def _format_claims_as_context(data: dict[str, Any] | None) -> str:
    """Render the claim-derived dict as inline context lines for the
    catalogue prompt. The Extract* nodes already wrote KnowledgeClaim
    rows; this surfaces them to the LLM so its narrative paragraph is
    informed by typed entities (not just the raw transcripts).
    Daniel: 'catalogue should take the output of all the previous ones
    and add it together'.
    """
    if not data:
        return ""
    lines: list[str] = []
    if people := data.get("personas_clave"):
        names = [p.get("nombre", "") if isinstance(p, dict) else str(p) for p in people]
        names = [n for n in names if n]
        if names:
            lines.append(f"People found: {', '.join(names)}")
    if places := data.get("lugares"):
        names = [p.get("nombre", "") if isinstance(p, dict) else str(p) for p in places]
        names = [n for n in names if n]
        if names:
            lines.append(f"Places found: {', '.join(names)}")
    if orgs := data.get("organizaciones"):
        names = [o.get("nombre", "") if isinstance(o, dict) else str(o) for o in orgs]
        names = [n for n in names if n]
        if names:
            lines.append(f"Organizations found: {', '.join(names)}")
    if events := data.get("eventos_clave"):
        descs = [e.get("evento", "") if isinstance(e, dict) else str(e) for e in events]
        descs = [d for d in descs if d]
        if descs:
            lines.append("Events found:\n  - " + "\n  - ".join(descs))
    if dates := data.get("fechas"):
        bits = []
        for d in dates:
            if isinstance(d, dict):
                f = d.get("fecha_normalizada") or d.get("fecha") or ""
                if f:
                    bits.append(f)
        if bits:
            lines.append(f"Dates found: {', '.join(bits)}")
    if keywords := data.get("palabras_clave"):
        kws = [str(k) for k in keywords if k]
        if kws:
            lines.append(f"Keywords: {'; '.join(kws)}")
    return "\n".join(lines)


# Per-call character budget for on-device models (Apple Intelligence ≈ 4K
# tokens, conservative ~12K chars). Cloud models tolerate much more but
# also benefit from focused chunks: shorter context = sharper summaries.
# Triggers map-reduce when transcripts exceed this size.
_RESUMEN_CHUNK_SIZE = 12000


async def _generate_resumen(
    text: str,
    output_language: str,
    llm_config: LLMConfig,
    claim_context: str = "",
) -> str:
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
    transcripts alone. Returns empty string on failure.
    """
    if not text and not claim_context:
        return ""

    context_block = (
        f"\n\nExtracted entities (from prior workflow steps):\n{claim_context}\n"
        if claim_context else ""
    )

    # Single-shot path — text fits comfortably in any model's context window.
    if len(text) <= _RESUMEN_CHUNK_SIZE:
        prompt = (
            f"Write a 150-300 word narrative catalogue entry in {output_language} "
            f"summarizing the following document. Plain prose, no headers, "
            f"no bullet points, no JSON. Use the extracted entities listed below "
            f"to ground the narrative in concrete names, places, and dates."
            f"{context_block}"
            f"\n\n---\nSource transcriptions:\n{text}"
        )
        try:
            response = await chat(
                [{"role": "user", "content": prompt}],
                config=llm_config,
            )
        except Exception as exc:
            logger.warning(f"Catalogue: resumen LLM call failed ({exc}); using empty")
            return ""
        return response.strip()

    # Map-reduce path — text exceeds context window. Split, summarise each
    # chunk briefly, then synthesise the final paragraph from the chunk
    # summaries + entity context. Same shape as the legacy 7-step pipeline's
    # 'summary' step.
    chunks = _split_text_into_chunks(text, _RESUMEN_CHUNK_SIZE)
    logger.info(
        f"Catalogue: text {len(text)} chars > {_RESUMEN_CHUNK_SIZE} budget — "
        f"map-reducing across {len(chunks)} chunks"
    )

    chunk_summaries: list[str] = []
    for index, chunk in enumerate(chunks):
        chunk_prompt = (
            f"Summarize this section of an archival document in 3-5 sentences "
            f"in {output_language}. Focus on concrete names, dates, places, "
            f"and events. Plain prose, no headers, no bullets.\n\n"
            f"Section {index + 1} of {len(chunks)}:\n{chunk}"
        )
        try:
            chunk_text = await chat(
                [{"role": "user", "content": chunk_prompt}],
                config=llm_config,
            )
            chunk_summaries.append(chunk_text.strip())
        except Exception as exc:
            logger.warning(
                f"Catalogue: chunk {index + 1}/{len(chunks)} summary failed ({exc})"
            )

    if not chunk_summaries:
        return ""

    combined_summaries = "\n\n".join(
        f"Section {i + 1}: {s}" for i, s in enumerate(chunk_summaries)
    )
    final_prompt = (
        f"Write a 150-300 word narrative catalogue entry in {output_language} "
        f"that synthesizes the section summaries below into a single coherent "
        f"finding-aid abstract. Pack it with concrete facts: full names, exact "
        f"dates, place names, organizations, chain of events, outcomes. Plain "
        f"prose, no headers, no bullet points, no JSON."
        f"{context_block}"
        f"\n\n---\nSection summaries:\n{combined_summaries}"
    )
    try:
        response = await chat(
            [{"role": "user", "content": final_prompt}],
            config=llm_config,
        )
    except Exception as exc:
        logger.warning(f"Catalogue: final synthesis failed ({exc}); using empty")
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
