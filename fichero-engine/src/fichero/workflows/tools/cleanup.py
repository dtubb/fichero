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

import logging
from typing import Any

from pydantic import BaseModel, Field

from fichero.db import db_manager
from fichero.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.llm import (
    LLMConfig,
    apple_intelligence_fits_in_context,
    chat_structured_with_fallback,
)
from fichero.models import Artifact
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_write_target
from fichero.workflows.tools.progress import emit_progress_event
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
        "noun": "person",
        "entity_type": EntityType.person,
        "icon": "person.2.crop.square.stack",
        "color": "blue",
        "duplicate_rule": (
            "Two entries refer to the same person if their names match (full "
            "name vs. partial form of the SAME person, with or without "
            "title or initials), or one is clearly a misspelling, "
            "abbreviation, or accent variant of the other. Pick the most "
            "complete form (longest, with title if used in the document) "
            "as canonical.\n\n"
            "DO NOT merge possessive or relational references — 'Leidy's "
            "mother', 'Pedro's brother', 'the Captain's wife' denote "
            "DIFFERENT people related to Leidy / Pedro / the Captain. "
            "Substring overlap is NOT a duplicate signal; only treat two "
            "entries as the same person when they plausibly name the same "
            "individual."
        ),
    },
    {
        "key": "places",
        "display": "Places",
        "noun": "place",
        "entity_type": EntityType.location,
        "icon": "mappin.circle",
        "color": "green",
        "duplicate_rule": (
            "Two entries refer to the same place if names are spelling or "
            "accent variants (Bazán / Basán), abbreviations, or recognised "
            "alternate names of the same town, river, region, address, or "
            "geographic feature. Pick the form the document uses most often "
            "as canonical."
        ),
    },
    {
        "key": "organizations",
        "display": "Organizations",
        "noun": "organisation",
        "entity_type": EntityType.organization,
        "icon": "building.2.crop.circle",
        "color": "indigo",
        "duplicate_rule": (
            "Two entries refer to the same organisation if names are spelling "
            "variants, abbreviations (Cía. / Compañía, S.A. / Sociedad "
            "Anónima), or one is the long form and the other a short form. "
            "Pick the most complete form as canonical."
        ),
    },
    {
        "key": "dates",
        "display": "Dates",
        "noun": "date",
        "entity_type": None,  # claim-only; cleanup runs over claim text
        "icon": "calendar.badge.checkmark",
        "color": "orange",
        # Dates skip the LLM entirely — exact-string dedup on YYYY-MM-DD —
        # so this rule is unused, kept for shape consistency.
        "duplicate_rule": (
            "Two entries refer to the same date if their normalised "
            "YYYY-MM-DD strings are identical."
        ),
    },
    {
        "key": "events",
        "display": "Events",
        "noun": "event",
        "entity_type": EntityType.event,
        "icon": "star.circle",
        "color": "yellow",
        "duplicate_rule": (
            "Two entries refer to the same event if they describe the same "
            "incident, transaction, signing, meeting, voyage, ruling, "
            "death, or transfer — even when worded differently or seen from "
            "different angles. Pick the most precise and concise description "
            "as canonical, in evidentiary phrasing ('the file records that "
            "X', 'Y is reported to have...'), with the alternative wordings "
            "as aliases."
        ),
    },
    {
        "key": "keywords",
        "display": "Keywords",
        "noun": "keyword",
        "entity_type": EntityType.concept,
        "icon": "tag.circle",
        "color": "pink",
        "duplicate_rule": (
            "Two entries are duplicates if they describe the same subject "
            "in different forms — singular vs. plural, language variant "
            "(mining / minería), or one is a more specific instance of the "
            "other. Pick the form the document uses, in Title Case."
        ),
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


def _build_cleanup_prompt(
    type_cfg: dict[str, Any], items: list[str],
) -> tuple[str, str]:
    """Return (instructions, user_prompt) for the dedup call.

    Rules + role go in instructions (Apple Intelligence's authoritative
    channel; mid/frontier models still treat as system message). The
    numbered list of items is the user prompt — untrusted input the
    model deduplicates without confusing for instructions (#815).
    """
    plural = type_cfg["display"].lower()
    noun = type_cfg["noun"]
    duplicate_rule = type_cfg["duplicate_rule"]
    n = len(items)

    instructions = (
        f"You are an expert archivist deduplicating {plural} extracted "
        f"from a document. Different entries may refer to the same "
        f"{noun} via spelling variants.\n\n"
        f"Duplicate rule: {duplicate_rule}\n\n"
        f"You are deduplicating, not curating. Every numbered input MUST "
        f"appear in your output as a canonical or as an alias — total "
        f"across all groups must equal {n}. Do NOT invent new entries.\n\n"
        f"Title Case the canonical (re-case ALL-CAPS entries). Keep "
        f"accents (María, José, Chocó). Entries with no duplicates "
        f"become their own group with empty aliases.\n\n"
        f"Return ONLY valid JSON, no prose, no fences:\n"
        f'{{"groups": [{{"canonical": "...", "aliases": '
        f'["...", "..."]}}, ...]}}'
    )
    numbered = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(items))
    user_prompt = numbered
    return (instructions, user_prompt)


def _normalize_case(name: str) -> str:
    """Title-case a name only if it's entirely uppercase. Preserves
    correctly-cased names ('von Neumann', 'de la Vega', 'O'Brien') and
    initials ('J. F. Kennedy') — only intervenes when OCR / archival
    convention shouted the whole thing.

    Counts only alphabetic characters when deciding "all caps" so trailing
    initials and punctuation don't muddy the test.
    """
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return name
    if all(c.isupper() for c in letters):
        return name.title()
    return name


class _DedupGroup(BaseModel):
    canonical: str = Field(
        description="The canonical (most complete / preferred) form of the name. "
        "Title Case. Re-cased from ALL-CAPS, accents preserved."
    )
    aliases: list[str] = Field(
        default_factory=list,
        description=(
            "Other surface forms in the input that refer to the same entity "
            "as the canonical. Empty when the canonical has no duplicates."
        ),
    )


class _DedupResult(BaseModel):
    """Schema for the dedup LLM call. Total of canonicals + aliases must
    equal the number of input names — see the system prompt's 'You are
    deduplicating, not curating' rule. Backfilled in Python if the LLM
    drops inputs anyway."""

    groups: list[_DedupGroup] = Field(default_factory=list)


_MAX_DEDUP_DEPTH = 4  # 4 splits → 16 batches → ~250 names per batch (more than fits the 4K window)


async def _ask_llm_to_dedupe(
    type_cfg: dict[str, Any],
    names: list[str],
    llm_config: LLMConfig,
    _depth: int = 0,
) -> list[dict[str, Any]]:
    """Call the LLM and return [{canonical, aliases}, ...].

    Uses grammar-constrained structured output — Apple Intelligence via
    fm-bridge's DynamicGenerationSchema, frontier providers via
    LangChain `with_structured_output(method="function_calling")`. The
    decoder cannot emit invalid JSON, so the previous "Expecting ',
    ' delimiter" / "Unterminated string" failure modes (which silently
    returned [] and disabled cleanup for that section) are gone (#845).

    Returns [] only when no names were supplied. On LLM transport
    failure (network/auth/timeout), logs the error and returns the
    identity grouping (each name as its own canonical with no aliases),
    so the workflow continues with no merges rather than aborting.

    Reactive chunking (#848): when Apple Intelligence's typed (decoding)
    or (context_overflow) error fires — the prompt + schema + names list
    exceeded what the on-device 4K window could hold in one shot — split
    the names list in half and recurse. Bounded by `_MAX_DEDUP_DEPTH`
    so a fundamentally hostile input can't recurse forever; on cap-out
    we fall through to identity grouping. Cross-batch deduplication
    isn't done (the LLM only sees one half at a time); for very long
    lists this means no-op merges across batch boundaries — strictly
    better than dropping the whole section as before.
    """
    if len(names) < 2:
        return [{"canonical": names[0], "aliases": []}] if names else []

    display = type_cfg["display"]
    instructions, user_prompt = _build_cleanup_prompt(type_cfg, names)

    # Proactive overflow check (#848 / #854 reactive variant). For
    # Apple Intelligence's 4K context window, estimate whether prompt +
    # instructions + headroom for the dedup response fits BEFORE
    # submitting. If it doesn't, split now rather than waste a
    # generation attempt that will fail with (decoding). Cleanup's
    # response budget is generous (~768 tokens covers 50+ groups with
    # short canonicals + alias lists). Non-Apple providers (256K+
    # context) skip the check — they can absorb our prompts whole.
    if (
        llm_config.provider == "apple"
        and len(names) >= 4
        and _depth < _MAX_DEDUP_DEPTH
        and not apple_intelligence_fits_in_context(
            prompt=user_prompt,
            instructions=instructions,
            response_headroom=768,
        )
    ):
        mid = len(names) // 2
        logger.info(
            f"cleanup proactive split on {display} "
            f"({len(names)} names exceed Apple context, depth={_depth})"
        )
        left = await _ask_llm_to_dedupe(
            type_cfg, names[:mid], llm_config, _depth=_depth + 1,
        )
        right = await _ask_llm_to_dedupe(
            type_cfg, names[mid:], llm_config, _depth=_depth + 1,
        )
        return left + right

    try:
        result = await chat_structured_with_fallback(
            prompt=user_prompt,
            schema=_DedupResult,
            config=llm_config,
            system=instructions,
            # Schema is enforced at decode; instructions cover the
            # dedup policy. Skip the auto-injected schema dump on Apple
            # Intelligence to save prompt tokens (#843).
            include_schema_in_prompt=False,
        )
    except RuntimeError as runtime_exc:
        # Detect Apple Intelligence's typed (decoding) and
        # (context_overflow) error kinds. Both indicate the prompt +
        # schema + names list exceeded what the model could handle in
        # one shot. Split + recurse rather than fall through to identity.
        msg = str(runtime_exc)
        is_overflow = "(decoding)" in msg or "(context_overflow)" in msg
        if is_overflow and len(names) >= 4 and _depth < _MAX_DEDUP_DEPTH:
            mid = len(names) // 2
            logger.warning(
                f"cleanup hit overflow on {display} "
                f"({len(names)} names, depth={_depth}); splitting and retrying"
            )
            left = await _ask_llm_to_dedupe(
                type_cfg, names[:mid], llm_config, _depth=_depth + 1,
            )
            right = await _ask_llm_to_dedupe(
                type_cfg, names[mid:], llm_config, _depth=_depth + 1,
            )
            return left + right
        logger.warning(
            f"cleanup LLM call failed for {display}: {runtime_exc}; "
            f"returning identity grouping (no merges)"
        )
        return [{"canonical": _normalize_case(n), "aliases": []} for n in names]
    except Exception as exc:
        logger.warning(
            f"cleanup LLM call failed for {display}: {exc}; "
            f"returning identity grouping (no merges)"
        )
        return [{"canonical": _normalize_case(n), "aliases": []} for n in names]

    cleaned: list[dict[str, Any]] = []
    for g in result.groups:
        canonical = _normalize_case(g.canonical.strip())
        if not canonical:
            continue
        # Drop aliases that are casefold-equal to the canonical — they
        # render as redundant "(aka <self>)" suffixes in the inspector
        # (#825). Also drop empty / whitespace-only aliases and dedupe
        # within the alias list itself.
        canonical_key = canonical.casefold()
        aliases: list[str] = []
        seen_alias_keys: set[str] = {canonical_key}
        for a in g.aliases:
            text = a.strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen_alias_keys:
                continue
            seen_alias_keys.add(key)
            aliases.append(text)
        cleaned.append({"canonical": canonical, "aliases": aliases})

    # Backfill: the LLM may silently drop inputs it judges as "not a real
    # entry" even with the schema constraint. We are deduplicating, not
    # curating — every input must end up somewhere. Add anything missing
    # as its own single-item group.
    seen: set[str] = set()
    for g in cleaned:
        seen.add(g["canonical"].casefold())
        for a in g["aliases"]:
            seen.add(a.casefold())
    for name in names:
        if name.casefold() not in seen:
            cleaned.append({"canonical": _normalize_case(name), "aliases": []})
            seen.add(name.casefold())
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

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    # Use the write-target helper so single-file selections (incl. a
    # single PDF with page descendants) still get cleaned up (#1105).
    container = _resolve_write_target(selected_doc_ids, library_path)
    if not container or not library_path:
        return {"text": text, "records": records, "value": 0}

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning(f"page_cleanup({type_cfg['key']}): cannot open db: {exc}")
        return {"text": text, "records": records, "value": 0}

    # Resolve per-page doc IDs from the container's descendants. Don't trust
    # the records input — aggregate may emit empty doc_id when upstream
    # doesn't carry document metadata (transcribe → aggregate without the
    # documents port populated). Walking the doc tree is the source of truth.
    page_ids = [did for did in _descendant_doc_ids(db, container.id) if did != container.id]
    if not page_ids:
        return {"text": text, "records": records, "value": 0}

    merged_count = 0
    saved_count = 0
    artifact_type = f"{type_cfg['key']}_clean"
    for page_doc_id in page_ids:
        if entity_type is None:
            # Dates: claim-only, exact-string dedup on normalized YYYY-MM-DD.
            final_groups = _date_groups_for_doc(db, page_doc_id)
        else:
            entity_ids = _entity_ids_for_doc(db, page_doc_id)
            entities = _live_entities(db, entity_ids, entity_type)
            if not entities:
                continue
            names = [e.canonical_name for e in entities]
            if len(entities) >= 2:
                groups = await _ask_llm_to_dedupe(type_cfg, names, llm_config)
                merged_count += _apply_groups(db, entities, groups)
            else:
                groups = []
            final_groups = groups or [{"canonical": _normalize_case(n), "aliases": []} for n in names]

        if not final_groups:
            continue
        _replace_artifact(
            db,
            container_id=page_doc_id,
            artifact_type=artifact_type,
            groups=final_groups,
            provider=getattr(llm_config, "provider", None),
            model=getattr(llm_config, "model", None),
        )
        saved_count += 1

    logger.info(
        f"page_cleanup({type_cfg['key']}): merged {merged_count} entities, "
        f"wrote {artifact_type} on {saved_count}/{len(page_ids)} descendant docs"
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
    progress_callback = inputs.get("__progress_callback")
    entity_type = type_cfg["entity_type"]

    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    # Use the write-target helper so single-file selections (incl. a
    # single PDF with page descendants) still get cleaned up (#1105).
    container = _resolve_write_target(selected_doc_ids, library_path)
    if not container or not library_path:
        return {"text": text, "value": []}

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning(f"folder_cleanup({type_cfg['key']}): cannot open db: {exc}")
        return {"text": text, "value": []}

    descendant_ids = _descendant_doc_ids(db, container.id)

    if entity_type is None:
        # Dates: aggregate normalized YYYY-MM-DD across all descendants.
        # No LLM call — exact-string dedup is sufficient. Sort
        # chronologically: YYYY-MM-DD strings sort lexicographically,
        # which is also chronological order.
        total = max(len(descendant_ids), 1)
        seen: dict[str, dict[str, Any]] = {}
        for index, did in enumerate(descendant_ids, start=1):
            phase = f"{type_cfg['key']} clean scan {index}/{total}"
            await emit_progress_event(
                progress_callback,
                "file_start",
                "",
                phase,
                index,
                total,
                message=f"Clean scanning {type_cfg['key']} document {index}/{total}",
            )
            for grp in _date_groups_for_doc(db, did):
                key = grp["canonical"]
                if key not in seen:
                    seen[key] = grp
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                phase,
                index,
                total,
                message=f"Clean scanned {type_cfg['key']} document {index}/{total}",
            )
        if not seen:
            return {"text": text, "value": []}
        final_groups = sorted(seen.values(), key=lambda g: g["canonical"])
        merged = 0
    else:
        entity_ids: set[str] = set()
        total = max(len(descendant_ids), 1)
        for index, did in enumerate(descendant_ids, start=1):
            phase = f"{type_cfg['key']} clean scan {index}/{total}"
            await emit_progress_event(
                progress_callback,
                "file_start",
                "",
                phase,
                index,
                total,
                message=f"Clean scanning {type_cfg['key']} document {index}/{total}",
            )
            entity_ids.update(_entity_ids_for_doc(db, did))
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                phase,
                index,
                total,
                message=f"Clean scanned {type_cfg['key']} document {index}/{total}",
            )
        entities = _live_entities(db, sorted(entity_ids), entity_type)
        if not entities:
            return {"text": text, "value": []}
        names = [e.canonical_name for e in entities]
        # Deterministic pre-pass: collapse exact-equal names (case +
        # whitespace insensitive) so the LLM only runs when there's real
        # near-duplicate work to do. Saves a 15-20s LLM call on Apple
        # Intelligence whenever the extractor already produced clean
        # output (the common case after the combined extract_all step).
        distinct: dict[str, str] = {}
        for n in names:
            key = " ".join(n.split()).casefold()
            if key not in distinct:
                distinct[key] = _normalize_case(n.strip())
        if len(distinct) <= 1:
            groups = [{"canonical": v, "aliases": []} for v in distinct.values()]
            merged = 0
        else:
            await emit_progress_event(
                progress_callback,
                "file_start",
                "",
                f"{type_cfg['key']} clean LLM dedupe",
                1,
                1,
                message=(
                    f"Clean deduping {len(distinct)} {type_cfg['key']} "
                    "entities with LLM"
                ),
            )
            groups = await _ask_llm_to_dedupe(
                type_cfg, list(distinct.values()), llm_config,
            )
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                f"{type_cfg['key']} clean LLM dedupe",
                1,
                1,
                message=f"Clean LLM dedupe completed for {type_cfg['key']}",
            )
            merged = _apply_groups(db, entities, groups)
        final_groups = sorted(
            groups or [{"canonical": v, "aliases": []} for v in distinct.values()],
            key=lambda g: g["canonical"].casefold(),
        )

    # Save cleaned list as an artifact on the folder doc so the inspector
    # has a single canonical view per type — separate from the per-page
    # extractor artifacts (those keep raw per-page provenance).
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


def _date_groups_for_doc(db, doc_id: str) -> list[dict[str, Any]]:
    """Build cleaned-date `groups` for a single document.

    Dates extractor saves claims with empty entity_ids and normalized date
    in metadata['date_normalized']. Group by normalized form, collect raw
    `date_text` strings as aliases. Sorted by normalized date.
    """
    try:
        claims = db.query(KnowledgeClaim, source_document_id=doc_id)
    except Exception:
        return []
    by_norm: dict[str, set[str]] = {}
    for c in claims:
        if c.entity_ids:
            continue
        meta = c.metadata or {}
        normalized = (meta.get("date_normalized") or "").strip()
        raw = (meta.get("date_text") or "").strip()
        if not normalized:
            continue
        by_norm.setdefault(normalized, set())
        if raw and raw != normalized:
            by_norm[normalized].add(raw)
    return [
        {"canonical": norm, "aliases": sorted(aliases)}
        for norm, aliases in sorted(by_norm.items())
    ]


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


# Sample prompt rendering — the runtime swaps these placeholder names for
# the real list of canonical names per page/folder. Showing the shape (with
# placeholders) is more honest than showing nothing.
_SAMPLE_NAMES = ["Don Mateo Restrepo", "Don Mateo", "D. Mateo"]


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
        default_prompt="\n\n---\nItems to deduplicate:\n".join(
            _build_cleanup_prompt(type_cfg, _SAMPLE_NAMES)
        ),
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
        default_prompt="\n\n---\nItems to deduplicate:\n".join(
            _build_cleanup_prompt(type_cfg, _SAMPLE_NAMES)
        ),
        sort_order=30 + _TYPES.index(type_cfg),
    )(_tool)
    return _tool


PAGE_CLEANUPS = {
    f"{t['key']}_page_cleanup": _make_page_cleanup(t) for t in _TYPES
}
FOLDER_CLEANUPS = {
    f"{t['key']}_folder_cleanup": _make_folder_cleanup(t) for t in _TYPES
}
