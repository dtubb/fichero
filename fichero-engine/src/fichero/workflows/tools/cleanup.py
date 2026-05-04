"""
Per-Section Canonical Cleanup Tools (#803, #804).

Twelve workflow tools — six page-level, six folder-level — that take the
raw extracted entities of a single type and ask an LLM to pick canonical
names + group aliases. Same per-entity-type breakdown as the extractors
because small models (Apple Intelligence) handle one focused task per
prompt much better than one mega-prompt with nine sections.

Pipeline shape:
    extractors (per page) → page_cleanup (per page) →
    folder_cleanup (across pages) → catalogue (narrative + timeline + keywords)

Page cleanup (`<entity>_page_cleanup`):
    For each page in `records`, look at the entities of this type that
    were claimed on that page, ask the LLM to merge near-duplicates into
    a canonical name with aliases, and re-point claims at the merged
    canonical KnowledgeEntity (via `merged_into_id`).

Folder cleanup (`<entity>_folder_cleanup`):
    Across every page descended from the container doc, take all canonical
    entities of this type, ask the LLM to pick a global canonical for each
    near-duplicate cluster, and save the cleaned list as an artifact on
    the FOLDER doc (one artifact per type).

Both tools degrade gracefully: empty input → empty output (no LLM call);
LLM failure → log + passthrough (no merges, no data loss).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fichero.db import db_manager
from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.llm import LLMConfig, chat
from fichero.models import Artifact
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_container_doc
from fichero.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
)
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


# Entity-type config table — mirrors extractors._SECTIONS but only for
# the six types that produce canonical KnowledgeEntity rows (dates are
# claim-only so cleanup doesn't apply).
_TYPES: list[dict[str, Any]] = [
    {
        "key": "people",
        "display": "People",
        "entity_type": EntityType.person,
        "icon": "person.2.crop.square.stack",
        "color": "blue",
    },
    {
        "key": "places",
        "display": "Places",
        "entity_type": EntityType.location,
        "icon": "mappin.circle",
        "color": "green",
    },
    {
        "key": "organizations",
        "display": "Organizations",
        "entity_type": EntityType.organization,
        "icon": "building.2.crop.circle",
        "color": "indigo",
    },
    {
        "key": "dates",
        "display": "Dates",
        "entity_type": None,  # claim-only; cleanup runs over claim text
        "icon": "calendar.badge.checkmark",
        "color": "orange",
    },
    {
        "key": "events",
        "display": "Events",
        "entity_type": EntityType.event,
        "icon": "star.circle",
        "color": "yellow",
    },
    {
        "key": "keywords",
        "display": "Keywords",
        "entity_type": EntityType.concept,
        "icon": "tag.circle",
        "color": "pink",
    },
]


# =============================================================================
# Shared ports
# =============================================================================


_PAGE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Passthrough text from the upstream extractor.",
        ),
        PortDef(
            id="records",
            name="Records",
            port_type="input",
            data_type=DataType.ARRAY,
            required=True,
            description=(
                "Per-page records [{doc_id, text}, ...] from the upstream "
                "Aggregate node. Page cleanup uses doc_id to scope its DB "
                "read to one page at a time."
            ),
        ),
    ],
    [],
)


_FOLDER_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Passthrough text from upstream.",
        ),
    ],
    [],
)


# =============================================================================
# LLM dedup contract
# =============================================================================


def _build_cleanup_prompt(display: str, names: list[str]) -> str:
    """Build the dedup prompt — given a list of names, return canonical
    groupings as JSON.

    The schema is intentionally tiny: a flat list of {canonical, aliases}
    objects. Small models (Apple Intelligence) handle this far better
    than nested or polymorphic schemas.
    """
    numbered = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(names))
    return (
        f"You are deduplicating extracted {display.lower()} from an "
        f"archival document. The following list contains near-duplicates "
        f"caused by spelling variants, abbreviations, or capitalisation:\n\n"
        f"{numbered}\n\n"
        f"Group near-duplicates together and pick the most complete spelling "
        f"as the canonical form. Preserve original spelling and capitalisation "
        f"for the canonical. Do NOT invent new names. If a name has no "
        f"duplicates, list it alone with empty aliases.\n\n"
        f"Return ONLY valid JSON in this exact shape (no prose, no fences):\n"
        f'{{"groups": [{{"canonical": "...", "aliases": ["...", "..."]}}, ...]}}\n'
    )


def _strip_fences(raw: str) -> str:
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


async def _ask_llm_to_dedupe(
    display: str,
    names: list[str],
    llm_config: LLMConfig,
) -> list[dict[str, Any]]:
    """Call the LLM and parse {groups: [{canonical, aliases}]}.

    Returns [] on any failure — caller treats that as "no merges".
    """
    if len(names) < 2:
        return [{"canonical": names[0], "aliases": []}] if names else []

    prompt = _build_cleanup_prompt(display, names)
    try:
        response = await chat(
            [{"role": "user", "content": prompt}],
            config=llm_config,
        )
    except Exception as exc:
        logger.warning(f"cleanup LLM call failed for {display}: {exc}")
        return []

    try:
        parsed = json.loads(_strip_fences(response))
    except json.JSONDecodeError as exc:
        logger.warning(f"cleanup JSON parse failed for {display}: {exc}")
        return []

    if not isinstance(parsed, dict):
        return []
    groups = parsed.get("groups")
    if not isinstance(groups, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        canonical = (g.get("canonical") or "").strip()
        if not canonical:
            continue
        raw_aliases = g.get("aliases") or []
        aliases = [
            str(a).strip() for a in raw_aliases
            if isinstance(a, (str, int, float)) and str(a).strip()
        ]
        cleaned.append({"canonical": canonical, "aliases": aliases})
    return cleaned


# =============================================================================
# Page cleanup
# =============================================================================


async def _run_page_cleanup(
    type_cfg: dict[str, Any],
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Per-page canonical pass for one entity type.

    Reads page_doc_ids from `records`, looks up KnowledgeEntity rows
    referenced by claims on each page, asks the LLM to group near-dupes,
    and applies the merge by setting `merged_into_id` on the absorbed
    rows + appending their old name to the canonical row's aliases.
    """
    text = inputs.get("text") or ""
    records = inputs.get("records") or []
    entity_type = type_cfg["entity_type"]

    # Date-only type: claim-only, no entities to merge — passthrough.
    if entity_type is None or not records:
        return {"text": text, "records": records, "value": []}

    library_path = state.get("library_path", "")
    if not library_path:
        return {"text": text, "records": records, "value": []}

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning(f"page_cleanup({type_cfg['key']}): cannot open db: {exc}")
        return {"text": text, "records": records, "value": []}

    merged_count = 0
    for rec in records:
        if not isinstance(rec, dict):
            continue
        page_doc_id = str(rec.get("doc_id") or "")
        if not page_doc_id:
            continue
        entity_ids = _entity_ids_for_doc(db, page_doc_id)
        entities = _live_entities(db, entity_ids, entity_type)
        if len(entities) < 2:
            continue
        names = [e.canonical_name for e in entities]
        groups = await _ask_llm_to_dedupe(type_cfg["display"], names, llm_config)
        merged_count += _apply_groups(db, entities, groups)

    logger.info(
        f"page_cleanup({type_cfg['key']}): merged {merged_count} entities "
        f"across {len(records)} pages"
    )
    return {"text": text, "records": records, "value": merged_count}


# =============================================================================
# Folder cleanup
# =============================================================================


async def _run_folder_cleanup(
    type_cfg: dict[str, Any],
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Cross-page global canonical pass + write a `<key>_clean` artifact
    on the folder doc.

    Aggregates ALL canonical entities of this type across the container's
    descendant pages, asks the LLM for global groupings, applies merges
    in the KG, and saves the cleaned list as a JSON artifact for the
    inspector to render.
    """
    text = inputs.get("text") or ""
    entity_type = type_cfg["entity_type"]

    if entity_type is None:
        # Date-only — no canonical entities to merge.
        return {"text": text, "value": []}

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_container_doc(selected_doc_ids, library_path)
    if not container or not library_path:
        return {"text": text, "value": []}

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning(f"folder_cleanup({type_cfg['key']}): cannot open db: {exc}")
        return {"text": text, "value": []}

    descendant_ids = _descendant_doc_ids(db, container.id)
    entity_ids: set[str] = set()
    for did in descendant_ids:
        entity_ids.update(_entity_ids_for_doc(db, did))
    entities = _live_entities(db, sorted(entity_ids), entity_type)
    if not entities:
        return {"text": text, "value": []}

    names = [e.canonical_name for e in entities]
    groups = await _ask_llm_to_dedupe(type_cfg["display"], names, llm_config)
    merged = _apply_groups(db, entities, groups)

    # Save cleaned list as an artifact on the folder doc so the inspector
    # has a single canonical view per type — separate from the per-page
    # extractor artifacts (those keep raw per-page provenance).
    final_groups = groups or [{"canonical": n, "aliases": []} for n in names]
    artifact_type = f"{type_cfg['key']}_clean"
    _replace_artifact(
        db,
        container_id=container.id,
        artifact_type=artifact_type,
        groups=final_groups,
        provider=getattr(llm_config, "provider", None),
        model=getattr(llm_config, "model", None),
    )

    logger.info(
        f"folder_cleanup({type_cfg['key']}): merged {merged} entities, "
        f"wrote {len(final_groups)} canonical groups to {artifact_type}"
    )
    return {"text": text, "value": final_groups}


# =============================================================================
# DB helpers
# =============================================================================


def _entity_ids_for_doc(db, doc_id: str) -> list[str]:
    """All entity IDs referenced by claims on a single document."""
    try:
        claims = db.query(KnowledgeClaim, source_document_id=doc_id)
    except Exception:
        return []
    out: set[str] = set()
    for c in claims:
        for eid in c.entity_ids or []:
            out.add(eid)
    return list(out)


def _live_entities(
    db, entity_ids: list[str], entity_type: EntityType
) -> list[KnowledgeEntity]:
    """Load entities by id, filter by type, drop already-merged rows."""
    out: list[KnowledgeEntity] = []
    seen: set[str] = set()
    for eid in entity_ids:
        if eid in seen:
            continue
        seen.add(eid)
        try:
            ent = db.get(KnowledgeEntity, eid)
        except Exception:
            continue
        if ent is None or ent.entity_type != entity_type:
            continue
        if ent.merged_into_id:
            continue
        out.append(ent)
    return out


def _descendant_doc_ids(db, container_id: str) -> list[str]:
    """Return container_id + all doc IDs whose parent is the container or
    a descendant. One-level deep covers the common case (folder → files →
    pages); deeper trees fall through one extra hop.
    """
    from fichero.models import Document

    out = [container_id]
    try:
        children = db.query(Document, parent_id=container_id)
    except Exception:
        return out
    for child in children:
        out.append(child.id)
        try:
            grand = db.query(Document, parent_id=child.id)
        except Exception:
            continue
        for g in grand:
            out.append(g.id)
    return out


def _apply_groups(
    db,
    entities: list[KnowledgeEntity],
    groups: list[dict[str, Any]],
) -> int:
    """Apply LLM groupings: pick one entity per group as canonical, point
    others at it via `merged_into_id`, and merge their names into the
    canonical's aliases.

    Returns the number of entities marked as merged (absorbed into another).
    Idempotent: re-running with the same groups doesn't re-merge or
    duplicate aliases.
    """
    if not groups:
        return 0

    by_name: dict[str, KnowledgeEntity] = {e.canonical_name: e for e in entities}
    merged = 0
    for group in groups:
        canonical_name = group.get("canonical")
        aliases = group.get("aliases") or []
        if not canonical_name:
            continue
        canonical_entity = by_name.get(canonical_name)
        if canonical_entity is None:
            continue
        absorbed_names = [a for a in aliases if a in by_name and a != canonical_name]
        if not absorbed_names:
            continue
        new_aliases = list(canonical_entity.aliases or [])
        for name in absorbed_names:
            absorbed = by_name[name]
            if absorbed.merged_into_id == canonical_entity.id:
                continue
            absorbed.merged_into_id = canonical_entity.id
            try:
                db.save(absorbed)
            except Exception as exc:
                logger.warning(f"merge save failed for {absorbed.id}: {exc}")
                continue
            if name not in new_aliases:
                new_aliases.append(name)
            merged += 1
        if new_aliases != (canonical_entity.aliases or []):
            canonical_entity.aliases = new_aliases
            try:
                db.save(canonical_entity)
            except Exception as exc:
                logger.warning(f"alias update failed for {canonical_entity.id}: {exc}")
    return merged


def _replace_artifact(
    db,
    container_id: str,
    artifact_type: str,
    groups: list[dict[str, Any]],
    provider: str | None,
    model: str | None,
) -> None:
    """Delete any prior `<key>_clean` artifact on the container and save a
    fresh one. Idempotent — reruns overwrite cleanly.
    """
    try:
        existing = db.query(
            Artifact, document_id=container_id, artifact_type=artifact_type
        )
    except Exception:
        existing = []
    for prior in existing:
        try:
            db.delete(prior)
        except Exception as exc:
            logger.warning(f"could not delete prior {artifact_type}: {exc}")

    content = "; ".join(g["canonical"] for g in groups)
    try:
        db.save(
            Artifact(
                document_id=container_id,
                artifact_type=artifact_type,
                content=content,
                data={"groups": groups},
                provider=provider,
                model=model,
            )
        )
    except Exception as exc:
        logger.warning(f"could not save {artifact_type} artifact: {exc}")


# =============================================================================
# Registration — six page + six folder tools
# =============================================================================


def _make_page_cleanup(type_cfg: dict[str, Any]):
    async def _tool(inputs, state, llm_config):
        return await _run_page_cleanup(type_cfg, inputs, state, llm_config)

    name = f"{type_cfg['key']}_page_cleanup"
    _tool.__name__ = name
    register_tool(
        name=name,
        display_name=f"Clean {type_cfg['display']} (page)",
        description=(
            f"Group near-duplicate {type_cfg['display'].lower()} within each "
            f"page using a focused LLM call. Re-points claims at the merged "
            f"canonical entity."
        ),
        category="llm",
        icon=type_cfg["icon"],
        color=type_cfg["color"],
        uses_llm=True,
        supports_batch=False,
        input_ports=_PAGE_INPUT_PORTS,
        output_ports=BASE_OUTPUT_PORTS,
        config_schema=BASE_CONFIG_SCHEMA,
        sort_order=20 + _TYPES.index(type_cfg),
    )(_tool)
    return _tool


def _make_folder_cleanup(type_cfg: dict[str, Any]):
    async def _tool(inputs, state, llm_config):
        return await _run_folder_cleanup(type_cfg, inputs, state, llm_config)

    name = f"{type_cfg['key']}_folder_cleanup"
    _tool.__name__ = name
    register_tool(
        name=name,
        display_name=f"Clean {type_cfg['display']} (folder)",
        description=(
            f"Pick global canonical {type_cfg['display'].lower()} across all "
            f"pages in the folder and save a cleaned artifact on the folder "
            f"doc."
        ),
        category="llm",
        icon=type_cfg["icon"],
        color=type_cfg["color"],
        uses_llm=True,
        supports_batch=False,
        input_ports=_FOLDER_INPUT_PORTS,
        output_ports=BASE_OUTPUT_PORTS,
        config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, {}),
        sort_order=30 + _TYPES.index(type_cfg),
    )(_tool)
    return _tool


PAGE_CLEANUPS = {
    f"{t['key']}_page_cleanup": _make_page_cleanup(t) for t in _TYPES
}
FOLDER_CLEANUPS = {
    f"{t['key']}_folder_cleanup": _make_folder_cleanup(t) for t in _TYPES
}
