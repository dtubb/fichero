"""
Combined entity extractor — ONE-SHOT AND TWO-STAGE MODES

ONE-SHOT MODE: One LLM call per page returns all six entity types (people,
places, organizations, dates, events, keywords) as a single JSON payload. This is the
speed-optimised default for Catalogue preset.

TWO-STAGE MODE: First pass extracts entity names only (no SVO pressure); second pass
runs per-entity claim extraction for grounded SVO + quotes. Better for provider paths
where one-shot tends to return weak/chatty SVO output.

Both modes produce the same output shape (people/places/organizations/dates/events/quotes
as lists of items with verb/object/source_text) so downstream tools (folder_cleanup,
KG writer) work unchanged. The node also emits a `kg_payload` write bundle so a
workflow can move KG persistence into an explicit downstream `kg_writer` node.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from fichero_server.core.timeutil import utc_now
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.db import db_manager
from fichero_server.llm import (
    LLMConfig,
    ProviderQuotaError,
    chat_structured,
    chat_structured_with_fallback,
    resolve_model_alias,
)
from fichero_server.models import Artifact, Document, DocType, FileType
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.catalogue import _resolve_write_target
from fichero_server.workflows.tools.extractors import (
    _SECTIONS,
    _split_into_pages,
    _render_section_markdown,
    _write_kg_rows,
)
from fichero_server.workflows.tools.llm_base import (
    BASE_CONFIG_SCHEMA,
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
)
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools._workflow_change_emit import (
    emit_workflow_kg_changes,
    emit_workflow_artifact_changes,
)
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


# Two-stage extraction configuration
TWO_STAGE_CONFIG = {
    "extraction_mode": {
        "type": "string",
        "enum": ["oneshot", "twostage"],
        "default": "oneshot",
        "description": (
            "Extraction mode. 'oneshot' uses one LLM call per page for all "
            "entity types. 'twostage' first extracts entity names only, then "
            "runs per-entity claim extraction for grounded SVO output."
        ),
    },
}

KG_WRITE_CONFIG = {
    "persist_kg": {
        "type": "boolean",
        "default": True,
        "description": (
            "Persist KG rows inline. Set false when an explicit downstream "
            "kg_writer node should own the write."
        ),
    },
}


# Sub-chunk budget — small on-device models (Apple Intelligence's ~4K
# token window) can't accept a full page of dense OCR; 3K chars leaves
# room for the combined-prompt overhead.
_MAX_CHUNK_CHARS = 3000
_LARGE_RUN_PAGE_COUNT = 50
_PROGRESS_LOG_EVERY_PAGES = 25


_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Aggregated text to extract from.",
        ),
        PortDef(
            id="records",
            name="Records",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description=(
                "Optional per-page records [{doc_id, text}, ...] from "
                "an upstream Aggregate node. When present, claims + "
                "artifacts save to PAGE doc_id (page-level KG)."
            ),
        ),
    ],
    [],
)


_LANGUAGE_CONFIG = {
    "output_language": {
        "type": "string",
        "default": "auto",
        "description": (
            "Output language. 'auto' detects from the source text "
            "(English / Spanish today)."
        ),
    },
}

_NER_CONFIG = {
    "ner_provider": {
        "type": "string",
        "default": "spacy",
        "description": "NER hint provider for extractor pre-pass: spacy, llm, or transformers",
    },
    "ner_model": {
        "type": "string",
        "default": "",
        "description": "Optional NER backend model (e.g. en_core_web_sm, en_core_web_trf)",
    },
}


async def _yield_page_work(
    phase: str,
    page_index: int,
    total_pages: int,
) -> None:
    """Cooperate with the server loop during large per-page batches.

    A 443-page catalogue run has thousands of small synchronous post-LLM
    steps. Each one is fine alone, but the uninterrupted loop can starve
    `/api/health`. Yield at page boundaries so unrelated requests get a
    chance to run between pages.
    """
    await asyncio.sleep(0)
    if (
        total_pages >= _LARGE_RUN_PAGE_COUNT
        and (
            (page_index + 1) % _PROGRESS_LOG_EVERY_PAGES == 0
            or page_index + 1 == total_pages
        )
    ):
        logger.info(
            "extract_all: %s progress %d/%d pages",
            phase,
            page_index + 1,
            total_pages,
        )


# SVO predicate fields shared across every entity-bearing section in
# the combined extract_all call. Mirrors the per-section schemas in
# extractors.py (`_SVO_VERB_FIELD` / `_SVO_OBJECT_FIELD`) so the
# combined call now produces structurally-identical output to the
# single-section path. (#1113 — without this the combined call left
# claim.predicate_verb / object_phrase NULL on every row.)
# Defaults make these optional so a model that returns a partial item
# (e.g. {name, source_text} with no verb/object, or a loose {name, fact})
# still validates and we salvage the entity/claim instead of failing the
# whole page with 66 "field required" errors → 0 claims. The prompt still
# asks for verb/object, so capable models fill them; this is the safety net.
_VERB = Field(
    default="",
    description="Specific predicate verb phrase.",
)
_OBJ = Field(
    default="",
    description="Specific object or complement.",
)
_SRC = Field(
    default="",
    description="Short exact supporting quote.",
)


class _Person(BaseModel):
    name: str
    verb: str = _VERB
    object: str = _OBJ
    source_text: str = _SRC


class _Place(BaseModel):
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _VERB
    object: str = _OBJ
    source_text: str = _SRC


class _Organization(BaseModel):
    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _VERB
    object: str = _OBJ
    source_text: str = _SRC


class _DateItem(BaseModel):
    date: str = Field(default="", description="as written")
    date_normalized: str = Field(
        default="", description="YYYY-MM-DD, YYYY-MM, YYYY, or range"
    )
    verb: str = _VERB
    object: str = _OBJ
    source_text: str = _SRC


class _Event(BaseModel):
    event: str = Field(description="event noun phrase")
    date: str | None = Field(default=None, description="date if stated")
    verb: str = _VERB
    object: str = _OBJ
    source_text: str = _SRC


class _Quote(BaseModel):
    name: str | None = Field(default=None, description="speaker name, or null")
    verb: str = Field(default="said", description="attribution verb")
    object: str = Field(default="", description="exact quote")
    source_text: str = Field(default="", description="short exact source phrase")


class _Extraction(BaseModel):
    """Schema for the combined extract_all call. Maps 1:1 onto the six
    section keys downstream tools (folder_cleanup, catalogue) expect."""

    people: list[_Person] = Field(default_factory=list)
    places: list[_Place] = Field(default_factory=list)
    organizations: list[_Organization] = Field(default_factory=list)
    dates: list[_DateItem] = Field(default_factory=list)
    events: list[_Event] = Field(default_factory=list)
    quotes: list[_Quote] = Field(
        default_factory=list,
        description="relevant direct quotes only",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="book-index terms",
    )
    additional_entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Custom entity types from the library registry. "
            "Keys are the registry type keys, values are lists of extracted names."
        ),
    )


# =============================================================================
# Two-Stage Extraction Schemas
# =============================================================================
#
# Stage 1: Entity-only extraction (no SVO pressure)
# These compact schemas get good name coverage from Apple Intelligence.
# Stage 2 runs per-entity claim extraction for grounded SVO.

class _EntityOnly(BaseModel):
    """Compact entity representation for Stage 1 (NER-only pass)."""
    name: str
    aliases: list[str] = Field(default_factory=list)
    # Optional with a sensible default so the Apple grammar stays permissive
    # per element. Making entity_type required (#1272) forced fm-bridge to
    # satisfy a nested all-required grammar on every chunk; on-device
    # FoundationModels can't, so the constrained decoder collapsed to `{}`.
    entity_type: str = "other"  # "person", "place", "organization", etc.


class _EntitiesOnly(BaseModel):
    """Stage 1 result: all entity names extracted."""
    # All fields optional (default_factory=list) so _pydantic_to_apple_schema
    # marks them `optional` in the Apple grammar. #1272 made them required to
    # stop a silent `{}` result, but an all-required nested grammar is
    # unsatisfiable for on-device FoundationModels and made the decoder
    # collapse to empty on EVERY chunk. We keep the grammar permissive and
    # detect a genuinely-empty Stage 1 result explicitly via
    # `_entities_only_is_empty` (soft failure), not by forcing the grammar.
    people: list[_EntityOnly] = Field(default_factory=list)
    places: list[_EntityOnly] = Field(default_factory=list)
    organizations: list[_EntityOnly] = Field(default_factory=list)
    dates: list[_EntityOnly] = Field(default_factory=list)
    events: list[_EntityOnly] = Field(default_factory=list)


class _SVOClaim(BaseModel):
    """Per-entity claim for Stage 2 extraction."""
    subject: str
    verb: str = Field(description="Specific predicate verb phrase.")
    object: str = Field(description="Specific object or complement.")
    source_text: str = Field(description="Verbatim quote from source.")
    epistemic_status: str = Field(default="tentative", description="confirmed/tentative/rejected")
    claim_type: str = Field(default="fact", description="fact/analysis/interpretation/argument")


class _EntityClaims(BaseModel):
    """Stage 2 result: grounded claims for a single entity."""
    subject: str
    claims: list[_SVOClaim] = Field(default_factory=list)


# =============================================================================
# Two-Stage Extraction Helpers
# =============================================================================

# Pronouns that may appear as the subject in a verbatim source_text excerpt
# when the LLM copies the quote directly. Detecting these lets us prepend the
# resolved entity name using archival bracket notation: [Entity Name] He had...
_SUBJECT_PRONOUNS = frozenset({
    "he", "she", "it", "they", "him", "her", "them",
    "his", "hers", "its", "their", "theirs",
    "i", "we", "us", "our", "ours",
})


def _annotate_pronoun_source(source_text: str, entity_name: str) -> str:
    """Prepend [Entity Name] when a source excerpt starts with a pronoun.

    Follows the archival convention where editors mark resolved references with
    square brackets so the excerpt is self-contained without altering the quote.
    """
    if not source_text or not entity_name:
        return source_text
    first_word = source_text.split()[0].rstrip(".,;:!?\"'").casefold()
    if first_word in _SUBJECT_PRONOUNS:
        return f"[{entity_name}] {source_text}"
    return source_text

def _entity_schema_in_prompt(llm_config: LLMConfig) -> bool:
    """Whether to inject the entity schema into the prompt for Stage 1.

    Apple on-device FoundationModels needs the schema in the prompt to
    actually populate a nested structured result: with
    ``include_schema_in_prompt=False`` the constrained decoder returns a
    grammar-valid but ALL-EMPTY object even on clean prose (#1633/#1634).
    Injecting the schema gives the model the field signal it needs and it
    extracts entities reliably. Other providers describe the shape via the
    system instructions and keep the flag ``False`` for token economy in
    cloud calls; only Apple flips to ``True``.
    """
    return llm_config.provider.lower() == "apple"


def _build_entity_only_instructions(output_language: str) -> str:
    """Stage 1 instructions - extract entity names only, no SVO pressure."""
    return (
        f"You are an expert archivist extracting entity names from a document. "
        f"Extract ONLY the entity names - no facts, no claims, just the names. "
        f"If a mention is obscured, do not guess it; keep any [ilegible] / "
        f"[uncertain] markers exactly as written. "
        f"Write in {output_language}.\n\n"
        f"Sections to extract:\n"
        f"- people: named people (proper names only)\n"
        f"- places: named places, regions, geographic areas\n"
        f"- organizations: named organizations, institutions, companies\n"
        f"- dates: dates as stated in the text (YYYY-MM-DD, YYYY-MM, or YYYY)\n"
        f"- events: named or described occurrences\n"
        f"\nReturn the entity names and any alternative spellings found."
    )


def _build_per_entity_claim_instructions(output_language: str) -> str:
    """Stage 2 instructions - extract grounded SVO claims for a specific entity."""
    return (
        f"You are extracting facts about a specific entity from a document. "
        f"Extract specific SVO (Subject-Verb-Object) claims about this entity. "
        f"For each claim, provide:\n"
        f"1. The predicate verb (e.g., 'served as', 'located in', 'wrote')\n"
        f"2. The object/complement (e.g., 'alcalde of Popayán', 'a mining region')\n"
        f"3. The exact source text where this claim appears, preserving any "
        f"   [ilegible] / [uncertain] markers and original accents exactly\n"
        f"Write in {output_language}. Only include facts directly supported by the text."
    )


async def _extract_entities_only(
    chunk_text: str,
    llm_config: LLMConfig,
    instructions: str,
    extraction_sem: asyncio.Semaphore,
    chunk_timings: list[float],
) -> _EntitiesOnly:
    """Stage 1: Extract entity names only (no SVO pressure)."""
    call_start = time.monotonic()
    try:
        async with extraction_sem:
            extraction = await chat_structured(
                prompt=chunk_text,
                schema=_EntitiesOnly,
                config=llm_config,
                system=instructions,
                include_schema_in_prompt=False,
                permissive_guardrails=True,
            )
    except ProviderQuotaError:
        raise
    except Exception as exc:
        elapsed = time.monotonic() - call_start
        chunk_timings.append(elapsed)
        logger.error(f"Stage 1 entity extraction failed: {exc}")
        raise
    elapsed = time.monotonic() - call_start
    chunk_timings.append(elapsed)
    return extraction


async def _extract_claims_for_entity(
    chunk_text: str,
    entity_name: str,
    entity_type: str,
    llm_config: LLMConfig,
    instructions: str,
    extraction_sem: asyncio.Semaphore,
) -> list[dict]:
    """Stage 2: Extract grounded claims for a single entity."""
    entity_prompt = (
        f"Entity: {entity_name}\n"
        f"Type: {entity_type}\n\n"
        f"Document text:\n{chunk_text}\n\n"
        f"Extract claims about '{entity_name}' from the text above."
    )
    try:
        async with extraction_sem:
            # Use fallback wrapper so guardrail/locale refusals on historical
            # content auto-retry on the user-configured $large model (#1254).
            result = await chat_structured_with_fallback(
                prompt=entity_prompt,
                schema=_EntityClaims,
                config=llm_config,
                system=instructions,
                include_schema_in_prompt=False,
                permissive_guardrails=True,
            )
        return [
            {
                "name": entity_name,
                "verb": claim.verb,
                "object": claim.object,
                "source_text": _annotate_pronoun_source(claim.source_text, entity_name),
                "epistemic_status": claim.epistemic_status,
                "claim_type": claim.claim_type,
            }
            for claim in result.claims
        ]
    except ProviderQuotaError:
        raise
    except Exception as exc:
        logger.warning(f"Stage 2 claim extraction failed for {entity_name}: {exc}")
        return []


def _convert_entities_to_extraction(
    entities: _EntitiesOnly,
    claims_by_entity: dict[str, list[dict]],
) -> _Extraction:
    """Convert two-stage results back to _Extraction format for compatibility."""
    people = []
    places = []
    organizations = []
    dates = []
    events = []

    for entity in entities.people:
        claims = claims_by_entity.get(entity.name, [])
        for c in claims:
            people.append(_Person(
                name=entity.name,
                verb=c.get("verb", ""),
                object=c.get("object", ""),
                source_text=c.get("source_text", ""),
            ))

    for entity in entities.places:
        claims = claims_by_entity.get(entity.name, [])
        for c in claims:
            places.append(_Place(
                name=entity.name,
                alternative_spellings=entity.aliases,
                verb=c.get("verb", ""),
                object=c.get("object", ""),
                source_text=c.get("source_text", ""),
            ))

    for entity in entities.organizations:
        claims = claims_by_entity.get(entity.name, [])
        for c in claims:
            organizations.append(_Organization(
                name=entity.name,
                alternative_spellings=entity.aliases,
                verb=c.get("verb", ""),
                object=c.get("object", ""),
                source_text=c.get("source_text", ""),
            ))

    for entity in entities.dates:
        claims = claims_by_entity.get(entity.name, [])
        for c in claims:
            dates.append(_DateItem(
                date=entity.name,
                date_normalized=entity.name,
                verb=c.get("verb", ""),
                object=c.get("object", ""),
                source_text=c.get("source_text", ""),
            ))

    for entity in entities.events:
        claims = claims_by_entity.get(entity.name, [])
        for c in claims:
            events.append(_Event(
                event=entity.name,
                verb=c.get("verb", ""),
                object=c.get("object", ""),
                source_text=c.get("source_text", ""),
            ))

    return _Extraction(
        people=people,
        places=places,
        organizations=organizations,
        dates=dates,
        events=events,
    )


# Built-in section keys — custom registry types must not collide with these.
_BUILTIN_EXTRACTION_KEYS = frozenset({
    "people", "places", "organizations", "dates", "events", "keywords",
})


def _normalize_custom_targets(raw: Any) -> list[str]:
    """Normalize workflow-provided custom extraction targets.

    Accepts a list[str] or comma-separated string. Returns lowercase keys,
    deduped, with built-in extractor keys removed.
    """
    if raw is None:
        return []

    values: list[str]
    if isinstance(raw, str):
        values = [part.strip() for part in raw.split(",")]
    elif isinstance(raw, list):
        values = [item.strip() for item in raw if isinstance(item, str)]
    else:
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if not key or key in _BUILTIN_EXTRACTION_KEYS:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _load_registry_types(db, library_path: str) -> list[str]:
    """Return enabled custom entity type keys from the per-library registry."""
    if not library_path:
        return []
    try:
        from fichero_server.models.knowledge import LibraryEntityType
        items = db.query(LibraryEntityType, library_id=library_path, enabled=True)
        return [
            item.entity_type_key
            for item in items
            if item.entity_type_key not in _BUILTIN_EXTRACTION_KEYS
        ]
    except Exception as exc:
        logger.warning("extract_all: could not load registry types for %s: %s", library_path, exc)
        return []


def _persist_additional_entities(
    db,
    additional_entities: dict[str, list[str]],
    target_doc_id: str,
) -> tuple[list[str], list[str]]:
    """Persist names extracted for custom registry types as KnowledgeEntity rows.

    Writes one KnowledgeEntity (entity_type=other) per extracted name with the
    type key stored in metadata["custom_entity_type_keys"] (a list so a name that
    appears under multiple custom types preserves all of them). Also writes a
    minimal KnowledgeClaim linking the entity to the source document so it
    participates in "which documents mention X?" queries just like built-in types.

    `target_doc_id` is the per-child page/image doc id when cataloguing a folder
    or multi-page PDF (the caller iterates chunks and passes each chunk's
    `page_doc_id or container.id`), so both the provenance claim's
    source_document_id and the entity's accumulated source_document_ids land on
    the right child — the parent then compiles the union via descendants
    (#1562 write-path).
    """
    container_id = target_doc_id
    from fichero_server.models.knowledge import KnowledgeEntity, EntityType
    from fichero_server.workflows.tools._entity_writer import save_claim, upsert_entity
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []

    for type_key, names in additional_entities.items():
        for name in names:
            name = name.strip()
            if not name:
                continue
            entity_id = upsert_entity(
                db,
                canonical_name=name,
                entity_type=EntityType.other,
                source_document_id=container_id,
            )
            if entity_id is None:
                continue
            written_entity_ids.append(entity_id)
            e = db.get(KnowledgeEntity, entity_id)
            if e is not None:
                # Append to list — don't clobber when the same name appears under
                # multiple custom types (e.g. "silver" tagged as both "minerals"
                # and "trade_goods").
                existing_keys: list[str] = e.metadata.get("custom_entity_type_keys") or []
                changed = False
                if type_key not in existing_keys:
                    existing_keys = [*existing_keys, type_key]
                    e.metadata = {**e.metadata, "custom_entity_type_keys": existing_keys}
                    changed = True
                if container_id and container_id not in (e.source_document_ids or []):
                    e.source_document_ids = [*(e.source_document_ids or []), container_id]
                    changed = True
                if changed:
                    db.save(e)
            # Minimal provenance claim — links entity to source document so KG
            # queries ("which docs mention X?") work for custom types just like
            # built-in types. No SVO at this stage; a follow-up pass can enrich.
            try:
                claim_id = save_claim(
                    db=db,
                    text=name,
                    source_document_id=container_id,
                    entity_ids=[entity_id],
                    subject_canonical=name,
                    metadata={"custom_entity_type_key": type_key},
                )
                if claim_id is not None:
                    written_claim_ids.append(claim_id)
            except Exception as exc:
                logger.warning(
                    "extract_all: failed to save provenance claim for custom entity %s/%s: %s",
                    type_key, name, exc,
                )
    return written_entity_ids, written_claim_ids


def _build_instructions(output_language: str, custom_entity_types: list[str] | None = None) -> str:
    """System instructions for the structured-output call. The schema
    itself is enforced at decode time (DynamicGenerationSchema on Apple,
    response_format=json_schema on LangChain providers); these
    instructions cover the things the schema can't express:
    - the language for prose fields
    - the don't-invent / cover-every-occurrence policy
    - per-section prose conventions reused from the individual extractors.
    """
    section_block = "\n".join([
        "- people: named people or named groups only. Extract specific "
        "facts about what they did, used, worked, produced, relied on, "
        "valued, or experienced. Do not use reporting verbs unless the "
        "text directly quotes or attributes speech.",
        "- places: named places or geographic regions with a specific "
        "relationship stated by the text. This includes geographic and "
        "land-use CATEGORIES, not just proper names: 'agricultural zones', "
        "'mining districts', 'territories' all belong here. If a term "
        "denotes a location or land area — even a generic one — it is a "
        "place, NOT a keyword/concept.",
        "- organizations: named organizations only.",
        "- dates: dates stated in the text, with the event or condition "
        "attached to that date.",
        "- events: occurrences explicitly stated by the text. This includes "
        "unnamed/generic occurrences: 'accident', 'flood', 'death', 'fire' "
        "are events, NOT keywords/concepts. If a term denotes something "
        "that happened, it is an event.",
        "- quotes: direct quotations only, where the source gives quoted "
        "words or an explicit speaker/writer attribution.",
        "- keywords: the 5-8 MOST SALIENT, distinctive keywords for "
        "ABSTRACT ideas only — themes, subjects, time periods, ideologies. "
        "Do NOT put places, events, people, or organizations here. If a term "
        "names a location (even 'agricultural zones') it belongs in places; "
        "if it names an occurrence (like 'accident' or 'flood') it belongs "
        "in events. Keywords are concepts, not concrete entities.",
    ])

    base = (
        f"You are an expert archivist extracting structured entities "
        f"from a document. Extract evidence, not ontology labels. Do "
        f"NOT emit generic claims like 'Pedro is a person', 'Colombia "
        f"is a location', or 'cash is a concept'. Entity type is "
        f"metadata only. For each useful entity or index term, extract "
        f"specific SVO facts grounded in nearby text, with source_text "
        f"as a short exact quote from the page, preserving any [ilegible] / "
        f"[uncertain] markers exactly as written. Cover repeated useful "
        f"facts for the same entity when the text supports them. Only "
        f"include facts the text supports — do not speculate or invent. "
        f"Keywords are book-index terms for finding this page later: "
        f"include relevant concepts, subjects, and names only when they "
        f"help locate the passage; do not pad to a quota. Write prose "
        f"fields in {output_language}. Use verbs from the page context "
        f"for ordinary claims. Reserve reporting verbs (said, stated, "
        f"declared, asserted, claimed, testified, petitioned, reported, "
        f"argued, wrote, denied, requested) for direct quotations or "
        f"explicitly attributed statements only.\n\n"
        f"Section-specific guidance:\n{section_block}"
    )
    if custom_entity_types:
        custom_lines = "\n".join(f"- {t}" for t in custom_entity_types)
        base += (
            f"\n\nThis library has custom entity types. "
            f"Extract them into the 'additional_entities' field as a mapping "
            f"of type key → list of entity names found in the text:\n{custom_lines}\n"
            f"Only include names clearly present in the source text."
        )
    return base


# Error-message fragments that mark a failure as systemic — it won't
# resolve by continuing, so every remaining chunk fails identically.
# Covers the canonical 0.0.2 case (no $large configured → the
# Apple-Intelligence fallback re-raises the same guardrail/decode error
# on every page) plus billing/network failures.
_SYSTEMIC_SIGNATURES = (
    "401", "403", "402",
    "quota", "rate limit", "rate_limit",
    "not configured", "no $large", "$large",
    "connection", "unreachable", "timed out", "timeout",
    "api key", "unauthorized", "forbidden",
)

# Fraction of chunks that must fail before we treat the run as systemically
# broken rather than partially degraded.
_SYSTEMIC_FAIL_FRACTION = 0.8
_SYSTEMIC_MIN_FAILED_CHUNKS = 3


def _record_text(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    text = record.get("text")
    return text.strip() if isinstance(text, str) else ""


def _normalize_records(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        text = _record_text(record)
        if not text:
            continue
        normalized.append({
            "index": record.get("index", index) if isinstance(record, dict) else index,
            "doc_id": str(record.get("doc_id") or "") if isinstance(record, dict) else "",
            "text": text,
        })
    return normalized


def _records_from_selected_documents(state: State) -> list[dict[str, Any]]:
    """Recover selected PDF/page text when upstream transcription is empty."""
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    if not library_path or not selected_doc_ids:
        return []

    try:
        db = db_manager.get_database(library_path)
    except Exception as exc:
        logger.warning("extract_all: could not open library for text recovery: %s", exc)
        return []
    if not hasattr(db, "get") or not hasattr(db, "query"):
        return []

    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_doc(doc: Document) -> None:
        if doc.id in seen:
            return
        seen.add(doc.id)
        metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
        raw_transcription = metadata.get("transcription")
        expected_text_length = metadata.get("text_length")
        if (
            isinstance(raw_transcription, str)
            and isinstance(expected_text_length, int)
            and expected_text_length > len(raw_transcription.strip()) + 50
            and doc.parent_id
        ):
            try:
                parent = db.get(Document, doc.parent_id)
                if parent and parent.path and parent.path.lower().endswith(".pdf"):
                    from fichero_server.workflows.tools.vision_base import _try_pdf_text_layer

                    page_texts = _try_pdf_text_layer(parent.path)
                    page_number = doc.sequence or metadata.get("page_number") or 1
                    page_index = int(page_number) - 1
                    if page_texts and 0 <= page_index < len(page_texts):
                        raw_transcription = page_texts[page_index]
            except Exception as exc:
                logger.debug(
                    "extract_all: could not recover full PDF page text for %s: %s",
                    doc.id,
                    exc,
                )
        text = (
            raw_transcription
            if isinstance(raw_transcription, str) and raw_transcription.strip()
            else doc.page_content or ""
        ).strip()
        if text:
            records.append({
                "index": len(records),
                "doc_id": doc.id,
                "text": text,
            })

    def visit(doc: Document) -> None:
        if doc.doc_type == DocType.folder:
            for child in db.query(Document, parent_id=doc.id):
                visit(child)
            return
        if doc.file_type == FileType.pdf:
            pages = db.query(Document, parent_id=doc.id, doc_type=DocType.page)
            if pages:
                for page in sorted(pages, key=lambda p: p.sequence or 0):
                    add_doc(page)
                return
        add_doc(doc)

    for doc_id in selected_doc_ids:
        doc = db.get(Document, doc_id)
        if doc is not None:
            visit(doc)
    return records


def _recover_text_and_records(
    inputs: dict[str, Any], state: State,
) -> tuple[str, list[dict[str, Any]]]:
    """Return usable extraction text + per-page records from all known sources."""
    records = _normalize_records(inputs.get("records"))
    raw_text = inputs.get("text")
    text = raw_text.strip() if isinstance(raw_text, str) else ""
    if records and text:
        return text, records
    if records and not text:
        text = "\n\n".join(record["text"] for record in records)
        return text, records

    outputs = state.get("outputs", {}) or {}
    fallback_text = text
    for node_id in ("transcribe", "aggregate", "files-source"):
        node_output = outputs.get(node_id)
        if not isinstance(node_output, dict):
            continue
        records = _normalize_records(node_output.get("records"))
        if records:
            return "\n\n".join(record["text"] for record in records), records
        # Vision/transcribe emits per-doc provenance as `page_records`.
        # If we read `text` first, we lose doc_id anchors and fall back to
        # container-scoped KG writes in twostage folder runs (#1403/#1404).
        page_records = _normalize_records(node_output.get("page_records"))
        if page_records:
            return (
                "\n\n".join(record["text"] for record in page_records),
                page_records,
            )
        node_text = node_output.get("text")
        if (
            not fallback_text
            and isinstance(node_text, str)
            and node_text.strip()
        ):
            # Keep scanning for structured records first (especially
            # `parallel_results.*.result.page_records`), then fall back to this.
            fallback_text = node_text.strip()

    parallel_records: list[dict[str, Any]] = []
    parallel_text_fallback_records: list[dict[str, Any]] = []
    parallel = state.get("parallel_results", {}) or {}
    for results in parallel.values():
        if not isinstance(results, list):
            continue
        for item in sorted(
            (r for r in results if isinstance(r, dict)),
            key=lambda r: r.get("index", 0),
        ):
            if not item.get("success"):
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            records = _normalize_records(result.get("records"))
            if records:
                parallel_records.extend(records)
                continue
            page_records = _normalize_records(result.get("page_records"))
            if page_records:
                parallel_records.extend(page_records)
                continue
            node_text = result.get("text")
            if isinstance(node_text, str) and node_text.strip():
                parallel_text_fallback_records.append({
                    "index": item.get("index", len(parallel_records)),
                    "doc_id": "",
                    "text": node_text.strip(),
                })
    if parallel_records:
        return "\n\n".join(record["text"] for record in parallel_records), parallel_records
    if parallel_text_fallback_records:
        return (
            "\n\n".join(record["text"] for record in parallel_text_fallback_records),
            parallel_text_fallback_records,
        )

    selected_records = _records_from_selected_documents(state)
    if selected_records:
        return "\n\n".join(record["text"] for record in selected_records), selected_records
    if fallback_text:
        return fallback_text, []
    return "", []


def _classify_systemic_error(
    errors: list[str], n_chunks: int
) -> str | None:
    """Decide whether a batch of chunk errors is *systemic* (#1060).

    Returns the representative cause string when the failure won't resolve
    by continuing — caller should set result["error"] so the builder
    raises SystemicErrorDetected and aborts the run. Returns None for
    genuinely-partial failures (a minority of sparse pages), which stay
    warn-and-continue.

    Two systemic signals:
    - an explicit infra signature (401/403, quota, "$large not configured",
      connection) present in any error, once at least half the chunks failed;
    - a sufficiently large batch of chunks failing at a high rate, or nearly
      all chunks failing with the *same* message (the $large-unconfigured /
      provider-down pattern, where every page re-raises an identical error).

    The minimum-failed-chunk guard matters for folder-scope extraction:
    when each page is its own one-chunk extract_all run, 1/1 or 1/2 transient
    page failures must warn-and-continue instead of aborting the whole folder.
    """
    if not errors or n_chunks <= 0:
        return None

    failed_chunks = len(errors)
    fail_fraction = failed_chunks / n_chunks
    infra_hit = next(
        (e for e in errors
         if any(sig in e.lower() for sig in _SYSTEMIC_SIGNATURES)),
        None,
    )
    most_common, count = Counter(errors).most_common(1)[0]
    repetitive = count / n_chunks >= _SYSTEMIC_FAIL_FRACTION
    enough_failures_for_pattern = failed_chunks >= _SYSTEMIC_MIN_FAILED_CHUNKS

    if (
        (enough_failures_for_pattern and fail_fraction >= _SYSTEMIC_FAIL_FRACTION)
        or (enough_failures_for_pattern and repetitive)
        or (infra_hit and fail_fraction >= 0.5)
    ):
        return infra_hit or most_common
    return None


_GENERIC_TYPE_OBJECTS = {
    "a person", "person",
    "a location", "location",
    "a place", "place",
    "an organization", "organization",
    "an organisation", "organisation",
    "an event", "event",
    "a concept", "concept",
    "a keyword", "keyword",
}


def _item_has_grounded_svo(item: Any) -> bool:
    if not isinstance(item, BaseModel):
        return False
    verb = str(getattr(item, "verb", "") or "").strip().casefold()
    obj = str(getattr(item, "object", "") or "").strip().casefold()
    source_text = str(getattr(item, "source_text", "") or "").strip()
    if not verb or not obj:
        return False
    if verb in {"is", "are", "was", "were"} and obj in _GENERIC_TYPE_OBJECTS:
        return False
    return bool(source_text)


def _extraction_is_empty(extraction: _Extraction) -> bool:
    return not any((
        extraction.people,
        extraction.places,
        extraction.organizations,
        extraction.dates,
        extraction.events,
        extraction.quotes,
        extraction.keywords,
    ))


def _entities_only_is_empty(entities: _EntitiesOnly) -> bool:
    """True when a Stage 1 result has no entities in any category.

    The Apple grammar is permissive (all categories optional), so an empty
    object is a valid decode. Detect that explicitly here and treat it as a
    soft failure (log / route to fallback) instead of relying on required
    grammar fields to raise — which collapsed the on-device decoder (#1272).
    """
    return not any((
        entities.people,
        entities.places,
        entities.organizations,
        entities.dates,
        entities.events,
    ))


def _extraction_is_thin(extraction: _Extraction, source_text: str = "") -> bool:
    """Reject name-list outputs that would become generic type claims."""
    if _extraction_is_empty(extraction) and len(source_text.strip()) > 200:
        return True
    items: list[BaseModel] = [
        *extraction.people,
        *extraction.places,
        *extraction.organizations,
        *extraction.dates,
        *extraction.events,
    ]
    if len(items) < 2:
        return False
    grounded = sum(1 for item in items if _item_has_grounded_svo(item))
    return grounded / len(items) < 0.5


async def _retry_thin_extraction_with_large(
    extraction: _Extraction,
    *,
    prompt: str,
    config: LLMConfig,
    system: str,
    include_schema_in_prompt: bool,
) -> _Extraction:
    """If Apple returns only entity names, retry on the configured $large."""
    if config.provider != "apple" or not _extraction_is_thin(extraction, prompt):
        return extraction
    try:
        large_provider, large_model = resolve_model_alias("$large", "")
    except ValueError:
        raise RuntimeError(
            "Apple returned thin SVO output and $large is not configured. "
            "Set Settings → AI Defaults → Default large model to enable "
            "grounded extraction fallback."
        )
    if large_provider == config.provider and large_model == config.model:
        return extraction
    fallback_config = LLMConfig(
        provider=large_provider,
        model=large_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        extra=dict(config.extra),
    )
    logger.warning(
        "extract_all: Apple returned thin SVO output; retrying on "
        "$large = %s/%s for grounded claims.",
        large_provider,
        large_model,
    )
    try:
        fallback_extraction = await chat_structured(
            prompt=prompt,
            schema=_Extraction,
            config=fallback_config,
            system=system,
            include_schema_in_prompt=include_schema_in_prompt,
        )
    except Exception as exc:
        raise RuntimeError(
            f"$large retry after thin Apple SVO output failed: {exc}"
        )
    if _extraction_is_thin(fallback_extraction, prompt):
        raise RuntimeError(
            "$large retry after thin Apple SVO output also returned empty "
            "or ungrounded extraction."
        )
    return fallback_extraction


def _build_entity_items_for_section(
    entity: Any, section_key: str, claims: list[dict]
) -> list[dict]:
    """Convert one two-stage entity + its Stage 2 claims to dicts for _write_kg_rows."""
    if section_key == "dates":
        return [
            {
                "date": entity.name,
                "date_normalized": entity.name,
                "verb": c.get("verb", ""),
                "object": c.get("object", ""),
                "source_text": c.get("source_text", ""),
            }
            for c in claims
        ]
    if section_key == "events":
        return [
            {
                "event": entity.name,
                "verb": c.get("verb", ""),
                "object": c.get("object", ""),
                "source_text": c.get("source_text", ""),
            }
            for c in claims
        ]
    # people, places, organizations
    return [
        {
            "name": entity.name,
            "alternative_spellings": getattr(entity, "aliases", []),
            "verb": c.get("verb", ""),
            "object": c.get("object", ""),
            "source_text": c.get("source_text", ""),
        }
        for c in claims
    ]


async def _run_two_stage(
    text: str,
    recovered_records: list[dict[str, Any]],
    state: State,
    llm_config: LLMConfig,
    output_language: str,
    inputs: dict[str, Any],
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Two-stage extraction: entity names first, then per-entity claims.

    Stage 1: Extract entity names only (NER pass, no SVO pressure)
    Stage 2: For each discovered entity, extract grounded SVO claims

    This produces more reliable grounded claims on Apple Intelligence
    where the one-shot prompt often produces weak/chatty SVO output.
    """
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_write_target(selected_doc_ids, library_path)

    # Build chunks
    records_input = recovered_records
    page_doc_ids: list[str | None] = []
    if records_input and isinstance(records_input, list):
        chunks = []
        for rec in records_input:
            if not isinstance(rec, dict):
                continue
            chunks.append(str(rec.get("text") or ""))
            page_doc_ids.append(str(rec.get("doc_id") or "") or None)
        if not chunks:
            chunks = _split_into_pages(text)
            page_doc_ids = [None] * len(chunks)
    else:
        chunks = _split_into_pages(text)
        page_doc_ids = [None] * len(chunks)

    _ = any(pid for pid in page_doc_ids)  # is_per_page info not needed in Stage 2
    entity_instructions = _build_entity_only_instructions(output_language)
    claim_instructions = _build_per_entity_claim_instructions(output_language)

    import os
    max_in_flight = int(os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT", "3"))
    extraction_sem = asyncio.Semaphore(max_in_flight)

    chunk_timings: list[float] = []
    chunk_errors: list[str] = []

    async def _run_stage1_one(idx: int, chunk_text: str) -> _EntitiesOnly:
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            f"Stage 1 chunk {idx + 1}/{len(chunks)}",
            idx + 1,
            len(chunks),
            message=f"Stage 1 extracting entities from chunk {idx + 1}/{len(chunks)}",
        )
        call_start = time.monotonic()
        try:
            async with extraction_sem:
                # Use fallback wrapper so guardrail/locale refusals auto-retry
                # on the user's configured $large model (#1254).
                extraction = await chat_structured_with_fallback(
                    prompt=chunk_text,
                    schema=_EntitiesOnly,
                    config=llm_config,
                    system=entity_instructions,
                    # Apple needs the schema in-prompt to populate the
                    # nested result; without it the on-device decoder
                    # returns an all-empty object even on clean prose
                    # (#1633/#1634). Other providers keep it off.
                    include_schema_in_prompt=_entity_schema_in_prompt(llm_config),
                    permissive_guardrails=True,
                )
        except Exception as exc:
            elapsed = time.monotonic() - call_start
            chunk_timings.append(elapsed)
            chunk_errors.append(str(exc))
            logger.error(f"Stage 1 chunk {idx} failed: {exc}")
            await emit_progress_event(
                progress_callback,
                "file_error",
                "",
                f"Stage 1 chunk {idx + 1}/{len(chunks)}",
                idx + 1,
                len(chunks),
                message=(
                    f"Stage 1 chunk {idx + 1}/{len(chunks)} failed "
                    f"after {elapsed:.1f}s"
                ),
                error=str(exc),
            )
            return _EntitiesOnly(
                people=[],
                places=[],
                organizations=[],
                dates=[],
                events=[],
            )
        elapsed = time.monotonic() - call_start
        chunk_timings.append(elapsed)
        entity_count = sum(
            len(getattr(extraction, f, []))
            for f in ["people", "places", "organizations", "dates", "events"]
        )
        logger.info(
            "Stage 1 chunk %s: found %s entities in %.1fs",
            idx,
            entity_count,
            elapsed,
        )
        # Explicit soft-fail detection: the Apple grammar is permissive, so an
        # all-empty decode is valid (not an exception). Log it so a genuinely
        # empty page is visible and a non-trivial page returning nothing is a
        # detectable signal rather than a silent zero-entity result (#1272).
        if _entities_only_is_empty(extraction) and len(chunk_text.strip()) > 200:
            logger.warning(
                "Stage 1 chunk %s: empty entity result on a %d-char chunk "
                "(provider=%s/%s) — treating as soft failure.",
                idx,
                len(chunk_text.strip()),
                llm_config.provider,
                llm_config.model,
            )
        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Stage 1 chunk {idx + 1}/{len(chunks)}",
            idx + 1,
            len(chunks),
            message=(
                f"Stage 1 chunk {idx + 1}/{len(chunks)} completed "
                f"in {elapsed:.1f}s"
            ),
        )
        return extraction

    # Stage 1: Extract all entity names
    logger.info(f"Stage 1: Extracting entity names from {len(chunks)} chunks")
    stage1_results = await asyncio.gather(
        *[_run_stage1_one(i, c) for i, c in enumerate(chunks)]
    )

    # Collect unique entities + track which chunks each appeared in.
    all_entities: dict[str, list[_EntityOnly]] = {
        "people": [],
        "places": [],
        "organizations": [],
        "dates": [],
        "events": [],
    }
    # entity_name → set of chunk indices where it was found
    entity_chunk_indices: dict[str, set[int]] = {}
    for chunk_idx, result in enumerate(stage1_results):
        for key in all_entities:
            for entity in getattr(result, key, []):
                if not entity.name:
                    continue
                if entity.name not in [e.name for e in all_entities[key]]:
                    all_entities[key].append(entity)
                entity_chunk_indices.setdefault(entity.name, set()).add(chunk_idx)

    # Stage 2: Extract claims for each entity using only the chunks it appeared in.
    # This avoids passing the full concatenated document and caps context to what
    # is actually relevant, giving the model the right page text for each entity.
    total_entities = sum(len(v) for v in all_entities.values())
    logger.info(f"Stage 2: Extracting claims for {total_entities} entities")

    persist_kg = inputs.get("persist_kg", True)
    kg_payload: list[dict[str, Any]] = []
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []
    written_document_ids: set[str] = set()
    _skip_sections = {"rivers_extract", "mines_extract", "properties_extract", "legal_references_extract"}
    _section_by_key = {s["schema_key"]: s for s in _SECTIONS}

    # Open DB once for incremental per-entity writes (#1263).
    db = None
    if container and library_path:
        try:
            db = db_manager.get_database(library_path)
        except Exception as exc:
            logger.error("extract_all (two-stage): cannot open DB for KG writes: %s", exc)

    all_claims: dict[str, list[dict]] = {}
    entity_jobs: list[dict[str, Any]] = []
    entity_done = 0
    for section_key, entities in all_entities.items():
        section = _section_by_key.get(section_key)
        for entity in entities:
            await emit_progress_event(
                progress_callback,
                "file_start",
                "",
                f"Stage 2 entity {entity_done + 1}/{total_entities}",
                entity_done + 1,
                total_entities,
                message=(
                    f"Stage 2 extracting claims for {section_key} "
                    f"'{entity.name}' ({entity_done + 1}/{total_entities})"
                ),
            )
            relevant_indices = sorted(entity_chunk_indices.get(entity.name, set()))
            if relevant_indices:
                entity_context = "\n\n".join(chunks[i] for i in relevant_indices)
            else:
                entity_context = text
            entity_jobs.append({
                "section_key": section_key,
                "section": section,
                "entity": entity,
                "relevant_indices": relevant_indices,
                "entity_context": entity_context,
                "claims_task": _extract_claims_for_entity(
                    entity_context,
                    entity.name,
                    section_key.rstrip("s"),
                    llm_config,
                    claim_instructions,
                    extraction_sem,
                ),
            })

    claim_results = await asyncio.gather(*(job["claims_task"] for job in entity_jobs))

    for job, claims in zip(entity_jobs, claim_results, strict=True):
        section_key = job["section_key"]
        section = job["section"]
        entity = job["entity"]
        relevant_indices = job["relevant_indices"]
        entity_context = job["entity_context"]
        all_claims[entity.name] = claims
        entity_done += 1
        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            f"Stage 2 entity {entity_done}/{total_entities}",
            entity_done,
            total_entities,
            message=(
                f"Stage 2 completed {section_key} '{entity.name}': "
                f"{len(claims)} claims"
            ),
        )
        logger.info(
            "Stage 2: %s/%s — %s '%s': %d claims",
            entity_done, total_entities, section_key, entity.name, len(claims),
        )

        # Write this entity's KG rows immediately — partial runs leave
        # partial KG instead of nothing (#1263 incremental resilience).
        # Guard on `container` (needed for container.id), not `db`: db is
        # only required for the optional inline write. When db=None the
        # payload is still built so the downstream kg_writer node can
        # persist it with its own connection (#1285).
        if section and section["name"] not in _skip_sections and claims and container:
            items = _build_entity_items_for_section(entity, section_key, claims)
            if items:
                target_indices = relevant_indices or [0]
                for page_idx in target_indices:
                    page_doc_id = (
                        page_doc_ids[page_idx]
                        if page_idx < len(page_doc_ids)
                        else None
                    )
                    target_doc_id = page_doc_id or container.id
                    page_label = (
                        f"Page {page_idx + 1}"
                        if len(chunks) > 1
                        else None
                    )
                    page_text = chunks[page_idx] if page_idx < len(chunks) else entity_context

                    kg_payload.append({
                        "section_name": section["name"],
                        "section_key": section_key,
                        "items": items,
                        "target_doc_id": target_doc_id,
                        "page_label": page_label,
                        "source_excerpt": page_text[:500] if page_text else None,
                        "provider": getattr(llm_config, "provider", None),
                        "model": getattr(llm_config, "model", None),
                        "grounding_text": page_text,
                    })
                    if persist_kg and db:
                        try:
                            entity_ids, claim_ids = _write_kg_rows(
                                db, section, items, target_doc_id,
                                page_label=page_label,
                                source_excerpt=page_text[:500] if page_text else None,
                                provider=getattr(llm_config, "provider", None),
                                model=getattr(llm_config, "model", None),
                                grounding_text=page_text,
                            )
                            written_entity_ids.extend(entity_ids)
                            written_claim_ids.extend(claim_ids)
                            written_document_ids.add(target_doc_id)
                        except Exception as exc:
                            logger.error(
                                "extract_all (two-stage): KG write failed for %s '%s' on %s: %s",
                                section_key,
                                entity.name,
                                target_doc_id,
                                exc,
                            )

    # Convert to extraction format for the return value.
    combined_entities = _EntitiesOnly(
        people=all_entities["people"],
        places=all_entities["places"],
        organizations=all_entities["organizations"],
        dates=all_entities["dates"],
        events=all_entities["events"],
    )
    extraction = _convert_entities_to_extraction(combined_entities, all_claims)

    # Use the same output format as oneshot mode
    _total_items = sum([
        len(extraction.people), len(extraction.places),
        len(extraction.organizations), len(extraction.dates), len(extraction.events),
    ])
    logger.info(
        "extract_all (two-stage): done — %d chunks, %d unique entities, "
        "%d entities with claims, %d KG rows queued",
        len(chunks), total_entities, entity_done, len(kg_payload),
    )
    if persist_kg and db and (written_entity_ids or written_claim_ids):
        emit_workflow_kg_changes(
            str(db.path.parent),
            entity_ids=written_entity_ids,
            claim_ids=written_claim_ids,
            document_ids=sorted(written_document_ids),
        )
    return {
        "text": _render_extraction_markdown(extraction),
        "value": {
            "people": [p.model_dump(mode="json") for p in extraction.people],
            "places": [p.model_dump(mode="json") for p in extraction.places],
            "organizations": [o.model_dump(mode="json") for o in extraction.organizations],
            "dates": [d.model_dump(mode="json") for d in extraction.dates],
            "events": [e.model_dump(mode="json") for e in extraction.events],
            "quotes": [],
            "keywords": [],
        },
        "kg_payload": kg_payload,
        "cached": False,
    }


def _render_extraction_markdown(extraction: _Extraction) -> str:
    """Render an extraction result as markdown."""
    parts = []
    for key, items in [
        ("people", extraction.people),
        ("places", extraction.places),
        ("organizations", extraction.organizations),
        ("dates", extraction.dates),
        ("events", extraction.events),
    ]:
        if items:
            items_text = "\n".join(
                f"- {getattr(item, 'name', None) or getattr(item, 'date', None) or getattr(item, 'event', '?')}: {item.verb} {item.object}".strip()
                for item in items
            )
            parts.append(f"## {key.title()}\n{items_text}")
    return "\n\n".join(parts) if parts else ""


async def extract_all(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Combined extractor — one LLM call per page returns all 6 types.

    Supports two modes:
    - oneshot (default): One LLM call per page for all entity types
    - twostage: First extracts entity names, then per-entity claims
    """
    progress_callback = inputs.get("__progress_callback")
    text, recovered_records = await asyncio.to_thread(
        _recover_text_and_records,
        inputs,
        state,
    )
    if not text:
        return {"text": "", "value": {}, "error": "No text input"}

    from fichero_server.llm.lang_detect import configured_primary_language, resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"),
        text,
        default="English",
        primary_language=configured_primary_language(),
    )

    # Keep the higher-quality twostage path on the three provider families
    # called out in #1807. Direct OpenAI/OpenRouter runs were still defaulting
    # to oneshot, so the same document extracted worse there than on Apple.
    provider_name = (llm_config.provider or "").lower()
    default_mode = (
        "twostage"
        if provider_name in {"apple", "openai", "openrouter"}
        else "oneshot"
    )
    extraction_mode = inputs.get("extraction_mode") or default_mode

    # Start banner (#1251) — visible in the activity log so long/stalled runs
    # show WHICH document is being worked on, not just per-chunk noise.
    _doc_ids = state.get("selected_doc_ids") or []
    _doc_hint = ",".join(d[:8] for d in _doc_ids[:3]) or "<none>"
    _num_records = len(recovered_records) if isinstance(recovered_records, list) else 0
    logger.info(
        "extract_all: start — doc=%s text=%d chars records=%d mode=%s provider=%s/%s",
        _doc_hint, len(text), _num_records, extraction_mode,
        llm_config.provider, llm_config.model,
    )

    if extraction_mode == "twostage":
        return await _run_two_stage(
            text, recovered_records, state, llm_config,
            output_language, inputs, progress_callback
        )

    # Onshot mode (existing behavior)
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_write_target(selected_doc_ids, library_path)

    # Per-page chunks via records (preferred) or text-split fallback.
    records_input = recovered_records
    page_doc_ids: list[str | None] = []
    if records_input and isinstance(records_input, list):
        chunks = []
        for rec in records_input:
            if not isinstance(rec, dict):
                continue
            chunks.append(str(rec.get("text") or ""))
            page_doc_ids.append(str(rec.get("doc_id") or "") or None)
        if not chunks:
            chunks = _split_into_pages(text)
            page_doc_ids = [None] * len(chunks)
    else:
        chunks = _split_into_pages(text)
        page_doc_ids = [None] * len(chunks)

    is_per_page = any(pid for pid in page_doc_ids)

    # Load per-library custom entity types from the registry (#1240).
    _registry_db = None
    custom_entity_types: list[str] = []
    if library_path:
        try:
            _registry_db = db_manager.get_database(library_path)
            custom_entity_types = _load_registry_types(_registry_db, library_path)
        except Exception as exc:
            logger.warning("extract_all: registry db open failed for %s: %s", library_path, exc)
    workflow_custom_types = _normalize_custom_targets(
        inputs.get("custom_extraction_targets") or inputs.get("extraction_targets")
    )
    if workflow_custom_types:
        merged = set(custom_entity_types)
        merged.update(workflow_custom_types)
        custom_entity_types = sorted(merged)

    instructions = _build_instructions(output_language, custom_entity_types)

    chunk_errors: list[str] = []
    # Per-page error tracking — when a chunk fails, we write an
    # `extraction_error` artifact on the page doc so the user can see
    # WHY a page came back empty (#800, #829).
    page_errors: list[str | None] = [None] * len(chunks)
    # Per-LLM-call wall-clock timings (#1037) — extract_all on a 15-page
    # PDF can run 20+ minutes; without per-call timing a slow run is
    # indistinguishable from a stuck one. Includes sub-chunk calls.
    chunk_timings: list[float] = []

    # Concurrency throttle for Apple Intelligence calls (#962 follow-up).
    # Apple Intelligence is a single-instance on-device model; firing
    # asyncio.gather() over 15+ chunks lets concurrent fm-bridge processes
    # compete for grammar-decoder state and thrash the local sampler,
    # which produces the "terminated generation early — Failed to
    # deserialize a Generable type" symptom on a non-trivial fraction of
    # chunks (reproduced on a Preface fixture).
    #
    # Cap at 3 concurrent — enough to keep the GPU busy without
    # serializing-by-default, but well below the thrash threshold.
    # Cloud-model chunks aren't affected by this because LangChain's
    # async paths don't hit fm-bridge; the semaphore still acquires
    # but the contention is on the upstream provider's rate limit,
    # not our local GPU. Make it tunable via env for future profiling.
    import os
    max_in_flight = int(os.environ.get("FICHERO_EXTRACT_MAX_IN_FLIGHT", "3"))
    extraction_sem = asyncio.Semaphore(max_in_flight)

    async def _extract_one(idx: int, chunk_text: str) -> dict[str, list]:
        # Sub-chunk if the page exceeds the small-model window. Apple
        # Intelligence's on-device window is ~4K tokens; chunks above
        # _MAX_CHUNK_CHARS get split and merged section-by-section.
        if len(chunk_text) > _MAX_CHUNK_CHARS:
            sub_chunks = [
                chunk_text[i:i + _MAX_CHUNK_CHARS]
                for i in range(0, len(chunk_text), _MAX_CHUNK_CHARS)
            ]
            sub_results = await asyncio.gather(
                *[_extract_one(-1, s) for s in sub_chunks]
            )
            merged: dict[str, list] = {}
            for sr in sub_results:
                for k, v in sr.items():
                    merged.setdefault(k, []).extend(v)
            return merged

        # Grammar-constrained call. On Apple Intelligence this routes
        # through fm-bridge's structured mode; on frontier providers
        # through LangChain's with_structured_output. Either way the
        # decoder cannot emit invalid JSON — the entire prompt-and-parse
        # failure class (Unterminated string, single-quoted JSON, prose
        # before/after the object) is gone (#799/#819 / #838 follow-up).
        # Use the fallback wrapper so guardrail refusals and
        # unsupported_language/locale errors (#1284) auto-retry on the
        # user's configured $large model instead of counting as chunk
        # failures and producing an empty catalogue.
        display_index = idx + 1 if idx >= 0 else len(chunk_timings) + 1
        display_total = len(chunks) if idx >= 0 else len(chunk_timings) + 1
        phase = f"Extract All chunk {display_index}/{display_total}"
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            phase,
            display_index,
            display_total,
            message=f"Extract All processing chunk {display_index}/{display_total}",
        )
        call_start = time.monotonic()
        try:
            async with extraction_sem:
                # Apple Intelligence (on-device) needs the schema echoed into
                # the prompt to populate the 6-section _Extraction structure.
                # Empirically, with include_schema_in_prompt=False the bridge's
                # grammar constraint alone collapses this large/nested schema to
                # `{}` — every field empty — whereas True yields fully-populated
                # people/places/dates/events. (The original #843 token-saving
                # rationale holds for small flat schemas but breaks _Extraction.)
                # The flag is Apple-only; LangChain providers ignore it, so a
                # provider check keeps the saving everywhere it's safe. (#1802)
                schema_in_prompt = llm_config.provider.lower() == "apple"
                extraction = await chat_structured_with_fallback(
                    prompt=chunk_text,
                    schema=_Extraction,
                    config=llm_config,
                    system=instructions,
                    include_schema_in_prompt=schema_in_prompt,
                )
                if _extraction_is_thin(extraction, chunk_text):
                    # Thin output normally triggers an auto-fallback to $large;
                    # when that isn't configured, KEEP the sparse extraction
                    # rather than discarding the whole page. Short diary pages
                    # legitimately yield few entities — failing them produced
                    # 0 claims across the run. (#1803)
                    logger.warning(
                        f"extract_all chunk {idx}: thin extraction output — "
                        "keeping it (no auto-fallback configured)"
                    )
        except ProviderQuotaError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - call_start
            chunk_timings.append(elapsed)
            msg = f"structured LLM call failed: {exc}"
            logger.error(
                f"extract_all chunk {idx} failed after {elapsed:.1f}s "
                f"({len(chunk_text)} chars) — {msg}"
            )
            chunk_errors.append(str(exc))
            if idx >= 0:
                page_errors[idx] = msg
            await emit_progress_event(
                progress_callback,
                "file_error",
                "",
                phase,
                display_index,
                display_total,
                message=(
                    f"Extract All chunk {display_index}/{display_total} failed "
                    f"after {elapsed:.1f}s"
                ),
                error=msg,
            )
            return {}

        elapsed = time.monotonic() - call_start
        chunk_timings.append(elapsed)
        logger.info(
            f"extract_all chunk {idx} extracted in {elapsed:.1f}s "
            f"({len(chunk_text)} chars)"
        )
        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            phase,
            display_index,
            display_total,
            message=(
                f"Extract All chunk {display_index}/{display_total} completed "
                f"in {elapsed:.1f}s"
            ),
        )

        # Pydantic instance → dict for the existing per-section pipeline
        # (KG writer, markdown renderer). Use mode="json" so URL-ish
        # primitives roundtrip as strings.
        return {
            "people": [p.model_dump(mode="json") for p in extraction.people],
            "places": [p.model_dump(mode="json") for p in extraction.places],
            "organizations": [
                o.model_dump(mode="json") for o in extraction.organizations
            ],
            "dates": [d.model_dump(mode="json") for d in extraction.dates],
            "events": [e.model_dump(mode="json") for e in extraction.events],
            "quotes": [q.model_dump(mode="json") for q in extraction.quotes],
            "keywords": list(extraction.keywords),
            "additional_entities": dict(extraction.additional_entities),
        }

    chunk_results: list[dict[str, list]] = await asyncio.gather(
        *[_extract_one(i, c) for i, c in enumerate(chunks)]
    )

    # Per-run timing summary (#1037) — tells slow-but-working apart from
    # stuck, and points at the slowest chunk for follow-up profiling.
    if chunk_timings:
        total_s = sum(chunk_timings)
        logger.info(
            f"extract_all: {len(chunk_timings)} LLM calls over "
            f"{len(chunks)} chunks — total {total_s:.1f}s, "
            f"slowest {max(chunk_timings):.1f}s, "
            f"avg {total_s / len(chunk_timings):.1f}s"
        )

    # Build per-section per-chunk lists for downstream save / markdown.
    per_section_chunks: dict[str, list[list[Any]]] = {
        s["schema_key"]: [] for s in _SECTIONS
    }
    for cr in chunk_results:
        for section in _SECTIONS:
            key = section["schema_key"]
            per_section_chunks[key].append(cr.get(key, []))

    persist_kg = inputs.get("persist_kg", True)
    kg_payload: list[dict[str, Any]] = []
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []
    written_document_ids: set[str] = set()
    created_artifact_ids: list[str] = []
    artifact_document_ids: set[str] = set()

    # Write errors and KG saves whenever we have a container/library —
    # even if every chunk failed, the per-page extraction_error
    # artifacts are valuable for diagnosis. The successful-data saves
    # below are guarded by `any(chunk_results)`.
    if container and library_path:
        try:
            db = _registry_db if _registry_db is not None else db_manager.get_database(library_path)
            # All writes go direct through the package's one shared connection;
            # the single per-package lock (#2508) serializes them, so the #1000
            # Phase-2 DBWriter queue is redundant and was removed (#2514).
            for section in _SECTIONS:
                key = section["schema_key"]
                # Skip sections that aren't in the default preset's
                # combined output (we filtered them in the prompt too).
                if section["name"] in {
                    "rivers_extract",
                    "mines_extract",
                    "properties_extract",
                    "legal_references_extract",
                }:
                    continue
                section_chunks = per_section_chunks.get(key, [])
                # KG write — per-page provenance.
                for page_idx, (chunk_text, items, page_doc_id) in enumerate(
                    zip(chunks, section_chunks, page_doc_ids)
                ):
                    phase = f"{key} KG write page {page_idx + 1}/{len(chunks)}"
                    await _yield_page_work(
                        phase,
                        page_idx,
                        len(chunks),
                    )
                    await emit_progress_event(
                        progress_callback,
                        "file_start",
                        "",
                        phase,
                        page_idx + 1,
                        len(chunks),
                        message=f"Extract All {phase}",
                    )
                    if not items:
                        await emit_progress_event(
                            progress_callback,
                            "file_complete",
                            "",
                            phase,
                            page_idx + 1,
                            len(chunks),
                            message=f"Extract All {phase}: no rows",
                        )
                        continue
                    page_label = f"Page {page_idx + 1}" if len(chunks) > 1 else None
                    excerpt = chunk_text[:500] if chunk_text else None
                    target_doc_id = page_doc_id or container.id
                    kg_payload.append(
                        {
                            "section_name": section["name"],
                            "section_key": key,
                            "items": items,
                            "target_doc_id": target_doc_id,
                            "page_label": page_label,
                            "source_excerpt": excerpt,
                            "provider": getattr(llm_config, "provider", None),
                            "model": getattr(llm_config, "model", None),
                            "grounding_text": chunk_text,
                        }
                    )
                    if persist_kg:
                        entity_ids, claim_ids = _write_kg_rows(
                            db, section, items, target_doc_id,
                            page_label=page_label, source_excerpt=excerpt,
                            provider=getattr(llm_config, "provider", None),
                            model=getattr(llm_config, "model", None),
                            grounding_text=chunk_text,
                        )
                        written_entity_ids.extend(entity_ids)
                        written_claim_ids.extend(claim_ids)
                        written_document_ids.add(target_doc_id)
                    await emit_progress_event(
                        progress_callback,
                        "file_complete",
                        "",
                        phase,
                        page_idx + 1,
                        len(chunks),
                        message=f"Extract All {phase}: {len(items)} rows",
                    )

                # Per-page artifact saves so the inspector + cache see
                # the right shape.
                if is_per_page:
                    for page_idx, (chunk_text, items, page_doc_id) in enumerate(
                        zip(chunks, section_chunks, page_doc_ids)
                    ):
                        await _yield_page_work(
                            f"{key} artifact save",
                            page_idx,
                            len(chunks),
                        )
                        if not page_doc_id or not items:
                            continue
                        page_md = _render_section_markdown(section, items)
                        artifact = Artifact(
                            document_id=page_doc_id,
                            artifact_type=section["artifact"],
                            content=page_md,
                            data={"items": items},
                            provider=getattr(llm_config, "provider", None),
                            model=getattr(llm_config, "model", None),
                            run_id=state.get("task_id"),
                        )
                        db.save(artifact)
                        created_artifact_ids.append(artifact.id)
                        artifact_document_ids.add(page_doc_id)
                else:
                    # Container-level fallback.
                    await _yield_page_work(f"{key} artifact save", 0, 1)
                    flat = [item for ic in section_chunks for item in ic]
                    if flat:
                        artifact = Artifact(
                            document_id=container.id,
                            artifact_type=section["artifact"],
                            content=_render_section_markdown(section, flat),
                            data={"items": flat},
                            provider=getattr(llm_config, "provider", None),
                            model=getattr(llm_config, "model", None),
                            run_id=state.get("task_id"),
                        )
                        db.save(artifact)
                        created_artifact_ids.append(artifact.id)
                        artifact_document_ids.add(container.id)
            # Per-page extraction_error artifacts: write one for each
            # page whose chunk failed, so the inspector can show WHY a
            # page came back empty (instead of indistinguishable from
            # "model genuinely found nothing"). #800, #829.
            if is_per_page:
                for page_idx, (err, page_doc_id) in enumerate(
                    zip(page_errors, page_doc_ids)
                ):
                    await _yield_page_work(
                        "extraction_error artifact save",
                        page_idx,
                        len(page_doc_ids),
                    )
                    if not err or not page_doc_id:
                        continue
                    artifact = Artifact(
                        document_id=page_doc_id,
                        artifact_type="extraction_error",
                        content=(
                            f"Page {page_idx + 1}: extraction failed.\n"
                            f"{err}\n\n"
                            "Try re-running with a different model, or "
                            "split the page if it's unusually large."
                        ),
                        data={
                            "page_index": page_idx,
                            "error": err,
                            "tool": "extract_all",
                        },
                        provider=getattr(llm_config, "provider", None),
                        model=getattr(llm_config, "model", None),
                        run_id=state.get("task_id"),
                    )
                    db.save(artifact)
                    created_artifact_ids.append(artifact.id)
                    artifact_document_ids.add(page_doc_id)
            # Persist custom entity types from the registry (#1240).
            #
            # #1562 write-path: scope each custom-entity name to the CHILD doc
            # (page/image) it was extracted from, not the parent container. We
            # accumulate per target_doc_id (page_doc_id or container.id) so a
            # name found on page 2 stamps page 2's id on both the provenance
            # claim and the entity's source_document_ids. Merging across all
            # chunks first (the old behaviour) collapsed everything onto the
            # folder, which is exactly the bug — selecting a child then showed
            # no per-child custom entities and the parent could not compile a
            # real descendant union.
            if custom_entity_types and persist_kg:
                custom_entity_type_set = set(custom_entity_types)
                # target_doc_id → {type_key → set(names)}; sets keep dedup O(n).
                by_doc: dict[str, dict[str, set[str]]] = {}
                for chunk_idx, cr in enumerate(chunk_results):
                    await _yield_page_work(
                        "custom entity merge",
                        chunk_idx,
                        len(chunk_results),
                    )
                    page_doc_id = (
                        page_doc_ids[chunk_idx]
                        if chunk_idx < len(page_doc_ids)
                        else None
                    )
                    target_doc_id = page_doc_id or container.id
                    for type_key, names in (cr.get("additional_entities") or {}).items():
                        if type_key not in custom_entity_type_set:
                            continue
                        bucket = by_doc.setdefault(target_doc_id, {}).setdefault(
                            type_key, set()
                        )
                        for name in (names or []):
                            name = name.strip() if isinstance(name, str) else ""
                            if name:
                                bucket.add(name)
                for target_doc_id, type_map in by_doc.items():
                    merged_additional = {
                        k: list(v) for k, v in type_map.items() if v
                    }
                    if merged_additional:
                        entity_ids, claim_ids = _persist_additional_entities(
                            db, merged_additional, target_doc_id
                        )
                        written_entity_ids.extend(entity_ids)
                        written_claim_ids.extend(claim_ids)
                        written_document_ids.add(target_doc_id)

            # Artifact writes above are direct + already durable (serialized on
            # the single per-package connection lock, #2508/#2514) — no queue to
            # drain before downstream folder-cleanup nodes read them.
            container.updated_at = utc_now()
            db.save(container)
            if persist_kg and (written_entity_ids or written_claim_ids):
                emit_workflow_kg_changes(
                    str(db.path.parent),
                    entity_ids=written_entity_ids,
                    claim_ids=written_claim_ids,
                    document_ids=sorted(written_document_ids),
                )
            if created_artifact_ids:
                emit_workflow_artifact_changes(
                    str(db.path.parent),
                    artifact_ids=created_artifact_ids,
                    document_ids=artifact_document_ids,
                )
        except Exception as exc:
            logger.error(f"extract_all: KG/artifact save failed: {exc}")

    # Aggregate everything into the value/text payload.
    value: dict[str, list] = {}
    for section in _SECTIONS:
        key = section["schema_key"]
        flat = [item for c in per_section_chunks.get(key, []) for item in c]
        if flat:
            value[key] = flat

    text_parts: list[str] = []
    for section in _SECTIONS:
        if section["name"] in {
            "rivers_extract", "mines_extract",
            "properties_extract", "legal_references_extract",
        }:
            continue
        items = value.get(section["schema_key"], [])
        text_parts.append(_render_section_markdown(section, items))
    markdown = "\n\n".join(text_parts)

    result: dict[str, Any] = {
        "text": markdown,
        "value": value,
        "kg_payload": kg_payload,
        "cached": False,
    }
    # Fail-fast on systemic errors (#1060). When a high fraction of
    # chunks fail — or they all fail with the same signature ($large
    # unconfigured, 401/403, quota, provider unreachable) — continuing is
    # pointless: every remaining page fails identically and the run
    # grinds out an empty "successful" catalogue. Setting result["error"]
    # makes the builder raise SystemicErrorDetected and abort the run
    # with the real cause (builder.py converts a tool's "error" key into
    # a hard abort). Genuinely-partial failures (a minority of sparse
    # pages) stay warn-and-continue — the per-page extraction_error
    # artifacts written above tell the user which pages to re-run.
    if chunk_errors:
        systemic_cause = _classify_systemic_error(chunk_errors, len(chunks))
        if systemic_cause:
            result["error"] = (
                f"Extract All: {len(chunk_errors)}/{len(chunks)} LLM calls "
                f"failed with a systemic error — {systemic_cause}"
            )
        else:
            logger.warning(
                f"extract_all: {len(chunk_errors)}/{len(chunks)} chunks "
                f"failed (partial extraction continued)"
            )

    _total_items = sum(len(v) for v in value.values())
    logger.info(
        "extract_all: done — doc=%s %d chunks → %d entities/events "
        "(%d KG rows queued)",
        _doc_hint, len(chunks), _total_items, len(kg_payload),
    )
    return result


register_tool(
    name="extract_all",
    display_name="Extract All Entities",
    description=(
        "Single-pass extraction of people, places, organisations, dates, "
        "events, and keywords. One LLM call per page returns all six "
        "types as JSON — 6× fewer calls than the per-type extractors, "
        "same downstream shape (KG claims + per-page artifacts)."
    ),
    category="llm",
    icon="square.grid.2x2",
    color="purple",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=_INPUT_PORTS,
    output_ports=merge_ports(
        BASE_OUTPUT_PORTS,
        [
            PortDef(
                id="kg_payload",
                name="KG Payload",
                port_type="output",
                data_type=DataType.JSON,
                description="Persistable KG write bundle",
            )
        ],
    ),
    config_schema=merge_config_schema(
        BASE_CONFIG_SCHEMA,
        _LANGUAGE_CONFIG,
        _NER_CONFIG,
        TWO_STAGE_CONFIG,
        KG_WRITE_CONFIG,
    ),
    default_prompt=_build_instructions("English"),
    sort_order=5,
)(extract_all)
