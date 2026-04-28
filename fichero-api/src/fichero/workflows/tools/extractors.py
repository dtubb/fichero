"""
Per-Section Catalogue Extractors

Eight standalone workflow tools covering the same nine catalogue sections
as ``catalogue.py``, but each extractor runs as its own node. Users build
custom pipelines with only the extractors they need — or swap one out for
a better implementation — without touching the monolithic ``catalogue``
tool.

Each extractor:
- Takes aggregated text (same shape catalogue consumes).
- Runs a focused LLM prompt asking ONLY for that section.
- Saves its own artifact keyed by the matching artifact_type
  ("people", "dates", "rivers", "events", "mines", "properties",
  "legal_references", "keywords") on the container document.
- Uses the same provider+model cache key as transcribe so repeated runs
  with the same model skip the LLM call.

The monolithic ``catalogue`` tool remains the fast default (one LLM
call for all nine sections); these are for researchers who want to
customize individual extractors or run just a subset.
"""

from __future__ import annotations

# EntityType import placed here so future authors see the KG mapping next
# to the section table below.
from fichero.knowledge_models import EntityType

import json
import logging
from datetime import datetime
from typing import Any

from fichero.db import db_manager
from fichero.llm import LLMConfig, chat
from fichero.models import Artifact
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_container_doc
from fichero.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    find_existing_artifact,
    merge_config_schema,
    merge_ports,
)
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


# =============================================================================
# Shared schema and config
# =============================================================================


_EXTRACTOR_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Aggregated text to extract from.",
        )
    ],
    [],
)


_LANGUAGE_CONFIG = {
    "output_language": {
        "type": "string",
        "default": "Spanish",
        "description": "Output language for extracted context.",
    },
}


# =============================================================================
# Section definitions — schema, instructions, artifact type
# =============================================================================
#
# Each entry:
#   name:         tool name (register + palette key)
#   display:      user-facing label
#   artifact:     matching artifact_type the UI already recognises
#   icon / color: palette appearance
#   schema_key:   top-level key in the returned JSON array
#   item_shape:   JSON shape each item must follow
#   instruction:  focused prompt text (what exactly to extract)


#   entity_type:  KG mapping — items become KnowledgeEntity rows of this
#                 EntityType (see _entity_writer.py). None means the section
#                 produces date-style claims with no canonical entity.
_SECTIONS: list[dict[str, Any]] = [
    {
        "name": "people_extract",
        "display": "Extract People",
        "artifact": "people",
        "entity_type": EntityType.person,
        "icon": "person.2",
        "color": "blue",
        "schema_key": "personas_clave",
        "item_shape": '{"nombre": "...", "contexto": "role and importance in __LANG__"}',
        "instruction": (
            "List the 5-15 most important people mentioned. For each: canonical name "
            "(preserve original spelling, capitalize properly), role and importance "
            "in the case. Group alternative spellings under the canonical (most "
            "complete) form."
        ),
    },
    {
        "name": "places_extract",
        "display": "Extract Places",
        "artifact": "places",
        "entity_type": EntityType.location,
        "icon": "mappin.and.ellipse",
        "color": "green",
        "schema_key": "lugares",
        "item_shape": (
            '{"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}'
        ),
        "instruction": (
            "List every named place — cities, towns, regions, countries, "
            "addresses, geographic features (excluding rivers, which have "
            "their own extractor). For each: canonical name (preserve "
            "original spelling, capitalize properly), alternative spellings "
            "found in the text, short context."
        ),
    },
    {
        "name": "organizations_extract",
        "display": "Extract Organizations",
        "artifact": "organizations",
        "entity_type": EntityType.organization,
        "icon": "building.2",
        "color": "indigo",
        "schema_key": "organizaciones",
        "item_shape": (
            '{"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}'
        ),
        "instruction": (
            "List every organization — companies, institutions, agencies, "
            "governmental bodies, religious orders, cooperatives. For each: "
            "canonical name + alternative spellings + context."
        ),
    },
    {
        "name": "dates_extract",
        "display": "Extract Dates",
        "artifact": "dates",
        "entity_type": None,  # date-style: claim only, no canonical entity
        "icon": "calendar",
        "color": "orange",
        "schema_key": "fechas",
        "item_shape": (
            '{"fecha": "as written", '
            '"fecha_normalizada": "YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD", '
            '"contexto": "..."}'
        ),
        "instruction": (
            "List every significant date. For each: the date as written in the "
            "original (with ambiguity if any), normalized to YYYY-MM-DD (or "
            "YYYY-MM-DD/YYYY-MM-DD for ranges, YYYY-MM for month-only), short "
            "context of what happened on or around that date."
        ),
    },
    {
        "name": "rivers_extract",
        "display": "Extract Rivers",
        "artifact": "rivers",
        "entity_type": EntityType.location,  # archive-specific subtype of location
        "icon": "water.waves",
        "color": "cyan",
        "schema_key": "rios",
        "item_shape": (
            '{"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}'
        ),
        "instruction": (
            "List every river, stream, waterway, or tributary mentioned. For each: "
            "canonical name, alternative spellings found in the text, context."
        ),
    },
    {
        "name": "events_extract",
        "display": "Extract Events",
        "artifact": "events",
        "entity_type": EntityType.event,
        "icon": "star",
        "color": "yellow",
        "schema_key": "eventos_clave",
        "item_shape": '{"evento": "...", "contexto": "..."}',
        "instruction": (
            "List significant events (incidents, decisions, hearings, meetings, "
            "deaths, transactions). Event description + surrounding context."
        ),
    },
    {
        "name": "mines_extract",
        "display": "Extract Mines",
        "artifact": "mines",
        "entity_type": EntityType.location,
        "icon": "pickaxe",
        "color": "brown",
        "schema_key": "minas",
        "item_shape": '{"nombre": "...", "contexto": "..."}',
        "instruction": (
            "List every mine, mining company, or mining claim mentioned. "
            "Name + context."
        ),
    },
    {
        "name": "properties_extract",
        "display": "Extract Properties",
        "artifact": "properties",
        "entity_type": EntityType.location,
        "icon": "building.columns",
        "color": "indigo",
        "schema_key": "propiedades",
        "item_shape": '{"nombre": "...", "contexto": "..."}',
        "instruction": (
            "List every property, estate, parcel, building, or farm mentioned "
            "that is not already a river or mine. Name + context."
        ),
    },
    {
        "name": "legal_references_extract",
        "display": "Extract Legal References",
        "artifact": "legal_references",
        "entity_type": EntityType.concept,  # legal references as conceptual citations
        "icon": "scale.3d",
        "color": "purple",
        "schema_key": "referencias_legales",
        "item_shape": '{"nombre": "...", "contexto": "..."}',
        "instruction": (
            "List every law, article, decree, statute, or legal reference "
            "cited. Name + context of how it's invoked."
        ),
    },
    {
        "name": "keywords_extract",
        "display": "Extract Keywords",
        "artifact": "keywords",
        "entity_type": EntityType.concept,
        "icon": "tag",
        "color": "pink",
        "schema_key": "palabras_clave",
        "item_shape": '"keyword"',  # flat array of strings
        "instruction": (
            "List 10-20 descriptive keywords capturing themes, subjects, "
            "locations, time periods, and legal concepts. Return as a flat "
            "array of short strings (no objects)."
        ),
    },
]


# =============================================================================
# Prompt + parse helpers (shared by all extractors)
# =============================================================================


def _build_section_prompt(section: dict[str, Any], output_language: str) -> str:
    """Focused extraction prompt for a single section.

    Returns ONLY a JSON object with the section's schema_key. Strict
    format keeps parsing simple and makes model output predictable.
    """
    item = section["item_shape"].replace("__LANG__", output_language)
    schema_key = section["schema_key"]
    shape = f'{{"{schema_key}": [{item}]}}'
    return (
        f"You are extracting a single section from archival text.\n\n"
        f"Task: {section['instruction']}\n\n"
        f"Rules:\n"
        f"- Include ALL occurrences.\n"
        f"- Only include facts supported by the text. Do not speculate.\n"
        f"- Write all prose in {output_language}.\n"
        f"- Return ONLY valid JSON matching this schema (no prose outside JSON):\n\n"
        f"{shape}\n"
    )


def _strip_fences(raw: str) -> str:
    """Strip ```json``` fences that some models emit around structured output."""
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _render_section_markdown(section: dict[str, Any], items: list[Any]) -> str:
    """Render a section's items as a small markdown fragment.

    Keyed off artifact type because each UI surface already knows how to
    render tags vs tables; the markdown here is the export fallback.
    """
    artifact_type = section["artifact"]
    if not items:
        return f"## {section['display']}\n\n_No entries found._\n"

    lines = [f"## {section['display']}", ""]
    if artifact_type == "keywords":
        lines.append(" · ".join(str(k) for k in items))
    elif artifact_type == "dates":
        for item in items:
            if isinstance(item, dict):
                date = item.get("fecha_normalizada") or item.get("fecha") or ""
                context = item.get("contexto") or ""
                lines.append(f"- **{date}** — {context}")
    else:
        for item in items:
            if isinstance(item, dict):
                primary_key = (
                    "nombre"
                    if artifact_type in {"people", "rivers", "mines", "properties", "legal_references"}
                    else "evento"
                )
                primary = item.get(primary_key) or item.get("nombre") or ""
                context = item.get("contexto") or ""
                lines.append(f"- **{primary}** — {context}")
    return "\n".join(lines) + "\n"


# =============================================================================
# Generic extractor implementation
# =============================================================================


async def _run_extractor(
    section: dict[str, Any],
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Shared body of every section extractor.

    Does cache lookup (by provider+model), LLM call, JSON parse, artifact
    save on the container doc, and returns the parsed items on the output
    port. Never raises — on failure returns an empty result and logs.
    """
    text = inputs.get("text") or ""
    if not text:
        return {"text": "", "value": [], "error": "No text input"}

    output_language = inputs.get("output_language", "Spanish")
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_container_doc(selected_doc_ids, library_path)

    # Cache: same (container, section, provider, model) reuses prior artifact.
    if container and library_path:
        cached = find_existing_artifact(
            document_id=container.id,
            file_path=None,
            artifact_type=section["artifact"],
            library_path=library_path,
            provider=getattr(llm_config, "provider", None),
            model=getattr(llm_config, "model", None),
        )
        if cached and cached.content:
            logger.info(
                f"{section['name']}: cache hit on {section['artifact']} for "
                f"{container.id} (provider={getattr(llm_config, 'provider', None)}, "
                f"model={getattr(llm_config, 'model', None)})"
            )
            cached_items = (
                cached.data.get("items") if isinstance(cached.data, dict) else None
            ) or []
            return {
                "text": cached.content,
                "value": cached_items,
                "cached": True,
            }

    prompt = _build_section_prompt(section, output_language)
    full_prompt = f"{prompt}\n\n---\nSource text:\n\n{text}"

    try:
        response = await chat(
            [{"role": "user", "content": full_prompt}],
            config=llm_config,
        )
    except Exception as exc:
        logger.error(f"{section['name']} LLM call failed: {exc}")
        return {"text": "", "value": [], "error": str(exc)}

    try:
        parsed = json.loads(_strip_fences(response))
    except json.JSONDecodeError as exc:
        logger.warning(f"{section['name']}: JSON parse failed ({exc}); saving raw")
        parsed = None

    items: list[Any] = []
    if isinstance(parsed, dict):
        raw_items = parsed.get(section["schema_key"])
        if isinstance(raw_items, list):
            items = raw_items
    elif isinstance(parsed, list):
        items = parsed

    markdown = _render_section_markdown(section, items)

    # Dual write: KG rows + markdown artifact.
    #
    # KG rows (KnowledgeEntity + KnowledgeClaim) are the queryable substrate
    # for cross-doc search and the 0.2.x KG layer (#728). Markdown artifacts
    # stay alongside as the human-readable / debug view (Daniel: "keep
    # markdown so we can debug as a user more easily"). Both writes are
    # idempotent on canonical_name+entity_type for entities; claims always
    # append (provenance trail).
    if container and library_path and items:
        try:
            db = db_manager.get_database(library_path)
            _write_kg_rows(db, section, items, container.id)
        except Exception as exc:
            logger.error(f"{section['name']}: KG write failed: {exc}")

    # Save artifact on the container (same doc catalogue writes to).
    if container and library_path:
        try:
            db = db_manager.get_database(library_path)
            artifact = Artifact(
                document_id=container.id,
                artifact_type=section["artifact"],
                content=markdown,
                data={"items": items} if items else None,
                provider=getattr(llm_config, "provider", None),
                model=getattr(llm_config, "model", None),
                run_id=state.get("task_id"),
            )
            db.save(artifact)
            # Bump container updated_at so the inspector refresh detects the change.
            container.updated_at = datetime.now()
            db.save(container)
            logger.info(
                f"{section['name']}: saved {section['artifact']} artifact "
                f"{artifact.id} on container {container.id}"
            )
        except Exception as exc:
            logger.error(f"{section['name']}: artifact save failed: {exc}")

    return {"text": markdown, "value": items, "cached": False}


def _write_kg_rows(
    db,
    section: dict[str, Any],
    items: list[Any],
    container_id: str,
) -> None:
    """Persist extractor items as KnowledgeEntity + KnowledgeClaim rows.

    Sections with ``entity_type`` set produce one entity per item (upsert
    by canonical_name) plus one claim linking the entity to the source
    document. Sections with ``entity_type=None`` (dates) produce claims
    only — the date itself is the claim, no canonical entity to dedup.
    """
    from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

    entity_type = section.get("entity_type")

    for item in items:
        if not isinstance(item, dict):
            # Keywords come through as bare strings — wrap minimally.
            item = {"nombre": str(item)}

        # Field names vary per section: nombre (most), evento (events),
        # fecha (dates). Try them in priority order so each extractor's
        # native shape produces a sensible canonical_name.
        canonical = (
            item.get("nombre")
            or item.get("name")
            or item.get("evento")
            or item.get("fecha")
            or ""
        )
        context = item.get("contexto") or item.get("context") or ""

        if entity_type is None:
            # Date-style section: claim only. Normalized date in metadata.
            date_text = item.get("fecha") or item.get("date") or canonical
            normalized = item.get("fecha_normalizada") or item.get("date_normalized") or ""
            claim_text = (
                f"{normalized or date_text}: {context}" if context
                else (normalized or date_text)
            )
            save_claim(
                db,
                text=claim_text,
                source_document_id=container_id,
                source_excerpt=context or None,
                metadata={
                    "date_text": date_text,
                    "date_normalized": normalized,
                },
            )
            continue

        # Entity-bearing section.
        if not canonical:
            continue
        aliases = (
            item.get("ortografias_alternativas")
            or item.get("alternative_spellings")
            or []
        )
        entity_id = upsert_entity(
            db,
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=aliases if isinstance(aliases, list) else [],
            description=context or None,
        )
        save_claim(
            db,
            text=f"{canonical}: {context}" if context else canonical,
            source_document_id=container_id,
            entity_ids=[entity_id],
            source_excerpt=context or None,
        )


# =============================================================================
# Registration — generate eight tools from the section list
# =============================================================================


def _make_registered(section: dict[str, Any]):
    """Wrap _run_extractor with section closure and register as a tool."""

    async def _tool(inputs, state, llm_config):
        return await _run_extractor(section, inputs, state, llm_config)

    _tool.__name__ = section["name"]

    register_tool(
        name=section["name"],
        display_name=section["display"],
        description=f"Extract {section['display'].replace('Extract ', '').lower()} section only.",
        category="llm",
        icon=section["icon"],
        color=section["color"],
        uses_llm=True,
        supports_batch=False,
        supports_structured_output=True,
        input_ports=_EXTRACTOR_INPUT_PORTS,
        output_ports=BASE_OUTPUT_PORTS,
        config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, _LANGUAGE_CONFIG),
        sort_order=10 + _SECTIONS.index(section),
    )(_tool)

    return _tool


# Exported so __init__.py importing this module triggers registration.
EXTRACTORS = {section["name"]: _make_registered(section) for section in _SECTIONS}
