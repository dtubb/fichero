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

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from fichero.db import db_manager
from fichero.llm import LLMConfig, chat_structured_with_fallback
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
        ),
        PortDef(
            id="records",
            name="Records",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description=(
                "Optional per-page records [{doc_id, text}, ...] from "
                "an upstream Aggregate node. When present, extractors "
                "iterate per page and save entity claims to the PAGE "
                "doc instead of the container. Enables page-level KG "
                "search."
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
            "(English / Spanish today); explicit names like 'English' "
            "or 'Spanish' pin the language regardless of input."
        ),
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
        "schema_key": "people",
        "item_shape": (
            '{"name": "...", "alternative_spellings": ["..."], '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List every PROPER NAME of a person — first name, surname, "
            "full name, with honorific or title when used. An entry must "
            "be a name a person would answer to. Skip pronouns, kinship "
            "terms without a name, generic groups, and role descriptions. "
            "Output: 'name' in Title Case (preserve original spelling "
            "and accents). The predicate is split into 'verb' + 'object' "
            "so the claim text composes as a real sentence: "
            "f'{name} {verb} {object}.' — name is the implicit subject, "
            "do NOT repeat it inside verb or object. "
            "Example: name='Eugenio Córdoba', verb='served as', "
            "object='the alcalde of Popayán'. Aliases are spelling "
            "variants of the SAME named person; never group different "
            "unnamed referents under one entry."
        ),
    },
    {
        "name": "places_extract",
        "display": "Extract Places",
        "artifact": "places",
        "entity_type": EntityType.location,
        "icon": "mappin.and.ellipse",
        "color": "green",
        "schema_key": "places",
        "item_shape": (
            '{"name": "...", "alternative_spellings": ["..."], '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List every named place — cities, towns, regions, countries, "
            "neighbourhoods, addresses, rivers, mines, estates. 'name' "
            "in Title Case (preserve original spelling and accents). "
            "'alternative_spellings' = spelling variants in the text. "
            "Predicate split into 'verb' + 'object' so the claim text "
            "composes as 'f'{name} {verb} {object}.' — name is the "
            "implicit subject. Example: name='Chocó', verb='is', "
            "object='the region where artisanal mining occurs'."
        ),
    },
    {
        "name": "organizations_extract",
        "display": "Extract Organizations",
        "artifact": "organizations",
        "entity_type": EntityType.organization,
        "icon": "building.2",
        "color": "indigo",
        "schema_key": "organizations",
        "item_shape": (
            '{"name": "...", "alternative_spellings": ["..."], '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List every NAMED organisation — companies, courts, ministries, "
            "banks, institutions, religious orders, schools, NGOs. Skip "
            "places, materials, occupations, and generic groups. 'name' "
            "in Title Case (preserve original spelling and accents). "
            "'alternative_spellings' = spelling variants in the text. "
            "Predicate split into 'verb' + 'object'. Example: "
            "name='Imprenta Oficial', verb='published', "
            "object='the official gazette of the Republic'."
        ),
    },
    {
        "name": "dates_extract",
        "display": "Extract Dates",
        "artifact": "dates",
        "entity_type": None,  # date-style: claim only, no canonical entity
        "icon": "calendar",
        "color": "orange",
        "schema_key": "dates",
        "item_shape": (
            '{"date": "as written", '
            '"date_normalized": "YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD", '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List every date in the text. 'date' = original wording. "
            "'date_normalized' = YYYY-MM-DD (range YYYY-MM-DD/YYYY-MM-DD; "
            "month-only YYYY-MM; year-only YYYY). The predicate describes "
            "what the document records for that date, split into 'verb' "
            "+ 'object'. The date is the implicit subject: claim text "
            "composes as 'f'{date}: {verb} {object}.' Example: "
            "verb='records', object='the filing of a mining petition by the heirs'."
        ),
    },
    {
        "name": "rivers_extract",
        "display": "Extract Rivers",
        "artifact": "rivers",
        "entity_type": EntityType.location,  # archive-specific subtype of location
        "icon": "water.waves",
        "color": "cyan",
        "schema_key": "rivers",
        "item_shape": (
            '{"name": "...", "alternative_spellings": ["..."], '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List every river, stream, waterway, or tributary mentioned. "
            "For each: canonical name, alternative spellings found in the "
            "text, predicate split into 'verb' + 'object'. Example: "
            "name='Atrato', verb='drains', object='the Chocó department "
            "westward to the Caribbean'."
        ),
    },
    {
        "name": "events_extract",
        "display": "Extract Events",
        "artifact": "events",
        "entity_type": EntityType.event,
        "icon": "star",
        "color": "yellow",
        "schema_key": "events",
        "item_shape": (
            '{"event": "Title Case noun phrase", '
            '"date": "YYYY-MM-DD or null", '
            '"verb": "...", "object": "..."}'
        ),
        "instruction": (
            "List significant events (incidents, decisions, hearings, "
            "deaths, transactions, petitions, rulings, transfers). "
            "'event' is a Title Case noun phrase naming the event "
            "(e.g. 'Mining Boom', 'Petition to the Court'). 'date' is "
            "YYYY-MM-DD (or YYYY-MM / YYYY) when stated, else null. "
            "Predicate split into 'verb' + 'object' (past tense). "
            "Example: event='Filing of the Petition', verb='was', "
            "object='submitted to the Constitutional Court by the heirs'."
        ),
    },
    {
        "name": "mines_extract",
        "display": "Extract Mines",
        "artifact": "mines",
        "entity_type": EntityType.location,
        "icon": "pickaxe",
        "color": "brown",
        "schema_key": "mines",
        "item_shape": '{"name": "...", "verb": "...", "object": "..."}',
        "instruction": (
            "List every mine, mining company, or mining claim mentioned. "
            "Name + predicate split into 'verb' + 'object'. Example: "
            "name='La Esperanza', verb='produces', object='alluvial gold "
            "in the upper Atrato basin'."
        ),
    },
    {
        "name": "properties_extract",
        "display": "Extract Properties",
        "artifact": "properties",
        "entity_type": EntityType.location,
        "icon": "building.columns",
        "color": "indigo",
        "schema_key": "properties",
        "item_shape": '{"name": "...", "verb": "...", "object": "..."}',
        "instruction": (
            "List every property, estate, parcel, building, or farm "
            "mentioned that is not already a river or mine. Name + "
            "predicate split into 'verb' + 'object'."
        ),
    },
    {
        "name": "legal_references_extract",
        "display": "Extract Legal References",
        "artifact": "legal_references",
        "entity_type": EntityType.concept,  # legal references as conceptual citations
        "icon": "scale.3d",
        "color": "purple",
        "schema_key": "legal_references",
        "item_shape": '{"name": "...", "verb": "...", "object": "..."}',
        "instruction": (
            "List every law, article, decree, statute, or legal reference "
            "cited. Name + predicate split into 'verb' + 'object' "
            "describing how it's invoked."
        ),
    },
    {
        "name": "keywords_extract",
        "display": "Extract Keywords",
        "artifact": "keywords",
        "entity_type": EntityType.concept,
        "icon": "tag",
        "color": "pink",
        "schema_key": "keywords",
        "item_shape": '"keyword"',  # flat array of strings
        "instruction": (
            "List descriptive keywords capturing themes, subjects, time "
            "periods, and concepts present in the text. Include only what the "
            "text actually discusses — no minimum count, no padding. Return as "
            "a flat array of short strings (no objects)."
        ),
    },
]


# =============================================================================
# Prompt + parse helpers (shared by all extractors)
# =============================================================================


# Per-section Pydantic schemas (#846). Each per-section extractor
# returns the same shape extract_all does for that section, just one
# section at a time. The shapes mirror extract_all._Person /._Place /
# etc. but live alongside the per-section tools so each can evolve
# independently.


# SVO claim composition (#730 / extractor refresh).
#
# Every extracted item carries `verb` + `object` instead of a free-form
# `context` string. The downstream KG writer composes the claim text
# deterministically as `"{name} {verb} {object}."` so claims always
# read as real sentences, and the structured triple lands in
# KnowledgeClaim.metadata for queryable use.
#
# - `verb`   = the predicate verb (or verb phrase): "is", "was", "served as",
#              "wrote", "founded", "located in", "described as".
# - `object` = the rest of the predicate after the verb: "the alcalde of
#              Popayán", "a gold-mining region in the Chocó".
# - The entity name is the implicit subject — never repeated in either
#   field.
_SVO_VERB_FIELD = Field(
    default="",
    description=(
        "Predicate verb or verb phrase. The entity name is the implicit "
        "subject — do NOT repeat it. Examples: 'is', 'was', 'served as', "
        "'wrote', 'founded', 'is located in'."
    ),
)
_SVO_OBJECT_FIELD = Field(
    default="",
    description=(
        "Rest of the predicate after the verb — a noun phrase or "
        "clause. Examples: 'the alcalde of Popayán', 'a gold-mining "
        "region in the Chocó', 'the deed of sale'."
    ),
)
# Epistemic status — drives the curation state of the resulting
# KnowledgeClaim. The LLM tags each item based on how firmly the
# source text asserts the claim. Default "tentative" so an LLM that
# omits the field still produces a safe (reviewable) claim. (#892)
_EPISTEMIC_FIELD = Field(
    # REQUIRED — see _SOURCE_TEXT_FIELD comment. (#894 option 2)
    description=(
        "How firmly the source text asserts this claim. "
        "'confirmed' = the text states the fact directly without "
        "hedging ('Pérez signed the deed'). "
        "'tentative' = hedged, reported, speculated, or attributed "
        "('Pérez may have signed', 'is said to have signed'). "
        "'rejected' = the text explicitly refutes the claim "
        "('Pérez did NOT sign'). When in doubt, use 'tentative'."
    ),
)
# Ontological status — what *kind* of knowledge the claim is. Peer
# axis to epistemic_status: epistemic = how firmly, ontological =
# what type. Drives downstream filtering / colour-coding in the KG
# inspector. Default "fact" because most NER-style extractions are
# concrete statements rather than analysis. (#892, peer to ClaimType
# on KnowledgeClaim.)
# Verbatim source excerpt — the exact sentence (or short paragraph)
# from the input text that the LLM lifted this claim from.
#
# REQUIRED in the JSON schema (no default) so grammar-constrained
# decoding on Apple Intelligence / fm-bridge forces the LLM to emit
# this field rather than skip it. A before-validator on each section
# model fills in "" for legacy items missing the field. (#894 option 2)
# Temporal scope (#904) — when in real-world time did this claim refer to?
# Distinct from when the claim was extracted (created_at). Empty string
# default — only populate when the source dates the claim.
_TIME_START_FIELD = Field(
    default="",
    description=(
        "Start of the time period the claim refers to, ISO 8601 "
        "('1933' or '1933-07-23'). Empty when the source doesn't "
        "date the claim. 'X became alcalde in 1933' → '1933'."
    ),
)
_TIME_END_FIELD = Field(
    default="",
    description=(
        "End of the time period. Equal to time_start for instant "
        "events ('signed the deed on 1933-07-23'); later for ranges "
        "('served from 1933 to 1937' → '1937'). Empty when the "
        "source doesn't bound the claim in time."
    ),
)

# Toulmin argument structure (#907) — populated only for analytic
# claim_types (analysis / argument / interpretation / theory). Default
# empty so fact claims stay flat.
_GROUNDS_FIELD = Field(
    default="",
    description=(
        "Evidence for an analytic claim. Only populate when the "
        "claim_type is analysis / argument / interpretation / theory. "
        "Example: for 'mining caused social fragmentation', grounds "
        "could be 'household-survey data showed 60% of mining-camp "
        "families had relatives elsewhere'. Empty for fact claims."
    ),
)
_WARRANT_FIELD = Field(
    default="",
    description=(
        "Rule linking grounds → claim for analytic claims. Example: "
        "'when household composition fractures, communities lose "
        "cohesion'. Empty for fact claims."
    ),
)

_SOURCE_TEXT_FIELD = Field(
    description=(
        "The exact sentence or short paragraph from the input text "
        "where this claim appears, copied verbatim (preserve original "
        "spelling, accents, punctuation). Quote the smallest span that "
        "still contains the full predicate. This text will be shown "
        "to the user and used to highlight the source span in the "
        "document — do NOT paraphrase or translate."
    ),
)
_CLAIM_TYPE_FIELD = Field(
    # REQUIRED — see _SOURCE_TEXT_FIELD comment. (#894 option 2)
    description=(
        "What kind of knowledge claim this is. "
        "'fact' = a concrete statement of what happened, who/what "
        "exists, or what is named ('Pérez signed the deed'). "
        "'analysis' = the source breaks the subject into parts or "
        "examines structure. "
        "'interpretation' = the source assigns meaning, motive, or "
        "significance. "
        "'argument' = the source advances a position with reasons. "
        "'historiography' = the source comments on how history has "
        "been written about the subject. "
        "'theory' = the source proposes a general model or framework. "
        "When in doubt, use 'fact'."
    ),
)


def _fill_required_defaults(data):
    """Before-validator factory: fill in defaults for the three
    required-but-defaultable fields when the input dict is missing
    them. Lets legacy artifacts (pre-#892 cache hits with the old
    item shape) still parse cleanly, while the JSON schema marks
    the fields ``required`` so Apple Intelligence's grammar forces
    fresh emissions. (#894 option 2)
    """
    if isinstance(data, dict):
        data.setdefault("epistemic_status", "tentative")
        data.setdefault("claim_type", "fact")
        data.setdefault("source_text", "")
    return data


class _SectionPerson(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    alternative_spellings: list[str] = Field(
        default_factory=list,
        description="other surface forms found in the text (e.g. M. García for María García)",
    )
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionPlace(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionOrganization(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionDate(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    # Dates are claim-only (no canonical entity). The `verb` + `object`
    # describe what happened on that date, not the date itself —
    # composed as `"{normalized}: {verb} {object}."` by the KG writer.
    date: str = Field(description="as written in the document")
    date_normalized: str = Field(
        description="YYYY-MM-DD (range YYYY-MM-DD/YYYY-MM-DD; month-only YYYY-MM; year-only YYYY)"
    )
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionRiver(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    alternative_spellings: list[str] = Field(default_factory=list)
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionEvent(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    event: str = Field(description="Title Case noun phrase naming the event")
    date: str | None = Field(default=None, description="YYYY-MM-DD when stated, else null")
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionMine(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionProperty(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


class _SectionLegalReference(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD
    grounds: str = _GROUNDS_FIELD
    warrant: str = _WARRANT_FIELD


def _make_section_schema(item_model: type[BaseModel], schema_key: str) -> type[BaseModel]:
    """Build a single-section wrapper Pydantic model. Each per-section
    tool returns `{<schema_key>: [<items>]}` so the parsed result has
    the same top-level shape as a slice of the extract_all output."""

    class SectionResult(BaseModel):
        # Use the section's schema_key as the field name via __fields__
        # injection so the generated JSON Schema names the property
        # consistently with extract_all's. We can't use a dynamic
        # field name with normal Pydantic syntax; this generates the
        # model class at module load.
        items: list[item_model] = Field(default_factory=list)  # type: ignore[valid-type]

    SectionResult.__name__ = f"_Section_{schema_key.title()}"
    return SectionResult


# Map schema_key → wrapper model. Used by _run_extractor's single-
# section LLM call. The wrapper carries the items under `items`
# regardless of section, so callers don't need a section-specific
# accessor.
_SECTION_SCHEMAS: dict[str, type[BaseModel]] = {
    "people": _make_section_schema(_SectionPerson, "people"),
    "places": _make_section_schema(_SectionPlace, "places"),
    "organizations": _make_section_schema(_SectionOrganization, "organizations"),
    "dates": _make_section_schema(_SectionDate, "dates"),
    "rivers": _make_section_schema(_SectionRiver, "rivers"),
    "events": _make_section_schema(_SectionEvent, "events"),
    "mines": _make_section_schema(_SectionMine, "mines"),
    "properties": _make_section_schema(_SectionProperty, "properties"),
    "legal_references": _make_section_schema(_SectionLegalReference, "legal_references"),
}


class _KeywordsResult(BaseModel):
    """Keywords are flat strings, not objects."""

    items: list[str] = Field(default_factory=list)


_SECTION_SCHEMAS["keywords"] = _KeywordsResult


def _build_section_prompt(section: dict[str, Any], output_language: str) -> str:
    """Focused extraction prompt for a single section.

    Returns ONLY a JSON object with the section's schema_key. Strict
    format keeps parsing simple and makes model output predictable.
    """
    item = section["item_shape"].replace("__LANG__", output_language)
    schema_key = section["schema_key"]
    shape = f'{{"{schema_key}": [{item}]}}'
    return (
        f"You are extracting a single section from a document.\n\n"
        f"Task: {section['instruction']}\n\n"
        f"Rules:\n"
        f"- Include ALL occurrences.\n"
        f"- Only include facts supported by the text. Do not speculate.\n"
        f"- Write all prose in {output_language}.\n"
        f"- For 'source_text', copy the exact sentence (or shortest "
        f"  paragraph) where the claim appears, verbatim — preserve "
        f"  original spelling, accents, and punctuation. Do NOT "
        f"  paraphrase or translate this field.\n"
        f"- For 'epistemic_status', tag tentative / confirmed / "
        f"  rejected based on how firmly the source asserts the claim.\n"
        f"- For 'claim_type', tag fact / analysis / interpretation / "
        f"  argument / historiography / theory based on what KIND of "
        f"  knowledge the claim is.\n"
        f"- For 'time_start' / 'time_end', ISO 8601 (year, year-month, "
        f"  or full date). Only populate when the source dates the claim "
        f"  ('became alcalde in 1933', 'on 23 July 1933'). Leave empty "
        f"  when the source is undated. For instant events, time_end "
        f"  equals time_start.\n"
        f"- For 'grounds' / 'warrant', only populate when claim_type is "
        f"  analysis / argument / interpretation / theory — these are "
        f"  the Toulmin-model components. 'grounds' = the evidence the "
        f"  source presents; 'warrant' = the rule connecting grounds to "
        f"  the claim. Leave empty for plain facts.\n"
        f"- Return ONLY valid JSON matching this schema (no prose outside JSON):\n\n"
        f"{shape}\n"
    )


def _split_into_pages(text: str) -> list[str]:
    """Split aggregated workflow text into per-page chunks.

    The aggregate node joins per-file/per-page transcripts with a
    ``\\n\\n---\\n\\n`` separator (its default). Splitting on the same
    boundary recovers the original chunks so each extractor can run a
    focused LLM call per page and attach per-page provenance to the
    resulting KG claims (#728).

    Falls back gracefully when the upstream isn't an aggregate (no
    separator present) — returns a single-element list with the full
    text. That preserves the pre-refactor single-pass behavior for
    workflows that don't use the aggregate node.
    """
    sep = "\n\n---\n\n"
    if not text:
        return []
    if sep not in text:
        return [text]
    return [chunk.strip() for chunk in text.split(sep) if chunk.strip()]


def _strip_fences(raw: str) -> str:
    """Strip wrapping that gets between us and the JSON object.

    Handles three common shapes that frontier cloud models (hit via the
    \$large guardrail fallback, #838) emit instead of bare JSON:

      1. Triple-backtick code fences (\\`\\`\\`json ... \\`\\`\\`)
      2. Explanatory prose before/after ("Here are the entities: { ... }")
      3. Both at once

    Strategy: strip fences first, then if the remainder doesn't already
    start with '{' or '[', slice from the first '{' to the matching last
    '}' (or '[' / ']' for arrays). Conservative — only triggers when the
    string isn't already clean JSON, so cases like "{...}" pass through
    unchanged.
    """
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped
    # Wrapping prose — pull out the first balanced JSON object/array.
    # The LLM's prompt asks for JSON, so the first { / [ is the start;
    # find the matching closer by depth count.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return stripped[start:i + 1].strip()
    return stripped


def _render_section_markdown(section: dict[str, Any], items: list[Any]) -> str:
    """Render a section's items as the artifact `content` field.

    The LLM returns these as JSON; the structured form lives in
    `Artifact.data["items"]`. This `content` was previously a markdown
    pretty-print but that obscured the underlying structure and made
    the inspector look like prose when it's actually editable data.
    Now stored as a JSON string so the inspector either renders it
    natively (Inspector V2, #156) or falls back to readable JSON.
    """
    if not items:
        return "[]"
    return json.dumps(items, ensure_ascii=False, indent=2)


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

    from fichero.lang_detect import resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"), text, default="English"
    )
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    container = _resolve_container_doc(selected_doc_ids, library_path)

    # Per-page extraction. Two paths:
    #   (a) records present (aggregate node passed [{doc_id, text}, ...])
    #       → iterate per record; cache + claims + artifact write to PAGE
    #         doc_id (per-file KG search + correct cache invalidation).
    #   (b) records absent (legacy / non-aggregate upstream)
    #       → split text on separator and write to container.id (legacy
    #         container-level cache + artifact save).
    records_input = inputs.get("records") or []
    page_doc_ids: list[str | None] = []
    if records_input and isinstance(records_input, list):
        chunks = []
        for rec in records_input:
            if not isinstance(rec, dict):
                continue
            chunks.append(str(rec.get("text") or ""))
            page_doc_ids.append(str(rec.get("doc_id") or "") or None)
        # If records were empty / malformed, fall back to text split.
        if not chunks:
            chunks = _split_into_pages(text)
            page_doc_ids = [None] * len(chunks)
    else:
        chunks = _split_into_pages(text)
        page_doc_ids = [None] * len(chunks)

    # Per-page records flow: cache check is per-page. If every page has a
    # cached artifact for (provider, model), short-circuit. Otherwise we
    # re-extract for ALL pages — keeping the parallel-extract code path
    # simple at the cost of redoing already-cached pages on partial misses.
    is_per_page = any(pid for pid in page_doc_ids)
    if is_per_page and container and library_path:
        all_cached_items: list[Any] = []
        all_cached_text_parts: list[str] = []
        every_page_cached = True
        for pid in page_doc_ids:
            if not pid:
                every_page_cached = False
                break
            cached = find_existing_artifact(
                document_id=pid,
                file_path=None,
                artifact_type=section["artifact"],
                library_path=library_path,
                provider=getattr(llm_config, "provider", None),
                model=getattr(llm_config, "model", None),
            )
            if cached and cached.content:
                if isinstance(cached.data, dict):
                    all_cached_items.extend(cached.data.get("items") or [])
                all_cached_text_parts.append(cached.content)
            else:
                every_page_cached = False
                break
        if every_page_cached:
            logger.info(
                f"{section['name']}: per-page cache hit on all "
                f"{len(page_doc_ids)} pages"
            )
            return {
                "text": "\n\n".join(all_cached_text_parts),
                "value": all_cached_items,
                "cached": True,
            }

    # Container-level cache (legacy / no records flow).
    if not is_per_page and container and library_path:
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

    # Sub-chunk budget — small on-device models (Apple Intelligence's
    # ~4K token window) can't accept a full page of dense handwritten
    # archive OCR (~7K tokens per page). Split each page into ~3K char
    # sub-chunks so prompt + sub-chunk fits comfortably. Cloud models
    # have much larger windows but extra splits are cheap and parallel.
    _MAX_CHUNK_CHARS = 3000

    # spaCy NER pre-pass (#899 Phase C). For people / places /
    # organizations / events sections we run spaCy first and pass the
    # detected mention list as a hint in the LLM prompt. Two wins:
    # 1. Sub-chunk dedup: even when we split a long page at 3000 chars,
    #    both sub-chunks see the same span list, so they produce one
    #    canonical entity name across them (down with the #896
    #    Davidson × 6 pattern). spaCy runs on the full chunk before
    #    splitting.
    # 2. Boundary consistency: the LLM trusts spaCy's PERSON / ORG /
    #    GPE / EVENT calls — no more "Eugenio Córdoba" vs "Mr Córdoba"
    #    drift between calls.
    # Sections without a matching spaCy label (dates, keywords, etc.)
    # bypass the hint and continue working unchanged.
    _SPACY_HINT_TYPES = {
        "people_extract": "person",
        "places_extract": "location",
        "organizations_extract": "organization",
        "events_extract": "event",
    }
    spacy_hint_lines: list[str] = []
    spacy_target = _SPACY_HINT_TYPES.get(section.get("name", ""))
    if spacy_target:
        try:
            from fichero.kg import spacy_ner

            all_spans = spacy_ner.extract_entities(text)
            relevant = [s for s in all_spans if s.fichero_type == spacy_target]
            clusters = spacy_ner.cluster_aliases(relevant)
            for canonical, aliases in clusters.items():
                if aliases:
                    spacy_hint_lines.append(
                        f"- {canonical.text} (aliases: {', '.join(aliases)})"
                    )
                else:
                    spacy_hint_lines.append(f"- {canonical.text}")
        except Exception as exc:
            # Don't take down the catalogue if spaCy is unhealthy.
            logger.warning("%s: spaCy pre-pass failed: %s", section["name"], exc)

    async def _extract_chunk(chunk_text: str) -> list[Any]:
        # Split a single page into sub-chunks if it exceeds the model's
        # context budget. Each sub-chunk gets its own LLM call; results
        # concatenate.
        if len(chunk_text) > _MAX_CHUNK_CHARS:
            sub_chunks = []
            for start in range(0, len(chunk_text), _MAX_CHUNK_CHARS):
                sub_chunks.append(chunk_text[start:start + _MAX_CHUNK_CHARS])
            sub_results = await asyncio.gather(
                *[_extract_one(s) for s in sub_chunks]
            )
            return [item for sub in sub_results for item in sub]
        return await _extract_one(chunk_text)

    # Track per-chunk LLM errors so we can distinguish "the document
    # genuinely has no entities" from "every LLM call hit a 403 / timeout
    # / parse failure". Without this, quota / auth / model-down errors
    # silently render as "_No entries found._" and the user has no clue
    # the cloud provider is rejecting calls (Daniel: "we need to do
    # better error checking — alert or something").
    chunk_errors: list[str] = []

    async def _extract_one(chunk_text: str) -> list[Any]:
        # Grammar-constrained structured output (#846). Mirrors
        # extract_all's migration: the decoder cannot emit invalid JSON
        # so the previous "JSON parse failed" failure mode is gone.
        # Apple Intelligence routes through fm-bridge structured mode;
        # frontier providers route through LangChain's
        # with_structured_output (json_schema or function_calling per
        # model.profile). Errors fall through to chunk_errors so the
        # caller can surface a meaningful message.
        section_schema = _SECTION_SCHEMAS.get(section["schema_key"])
        if section_schema is None:
            chunk_errors.append(f"no Pydantic schema for {section['schema_key']}")
            return []

        # Use Apple Intelligence's specialised contentTagging variant
        # when extracting keywords on Apple (#853). Apple's docs note
        # the variant produces crisper, semantically-grouped lowercase
        # tags ("hi"/"hello"/"yo" → one "greet" topic). Other sections
        # (people, places, etc.) use the general-purpose model since
        # they need rich entity attributes the tagging variant doesn't
        # produce. Other providers ignore use_case entirely.
        section_use_case = (
            "content_tagging" if section["schema_key"] == "keywords" else None
        )

        # Append spaCy-detected mentions to the prompt as a hint. The
        # LLM is instructed to use these as the canonical span set and
        # fold any extras into alternative_spellings rather than
        # inventing new entities.
        effective_system = prompt
        if spacy_hint_lines:
            hint_block = "\n".join(spacy_hint_lines)
            effective_system = (
                f"{prompt}\n\n"
                f"Pre-detected mentions in this section (use these as the "
                f"canonical entity set — fold parenthetical variants into "
                f"alternative_spellings rather than creating new items):\n"
                f"{hint_block}\n"
            )

        try:
            result = await chat_structured_with_fallback(
                prompt=chunk_text,
                schema=section_schema,
                config=llm_config,
                system=effective_system,
                # Per-section instructions describe the section
                # specifically; the schema describes the shape. Skip
                # the auto-injected schema dump on Apple Intelligence
                # to save the on-device 4K window (#843).
                include_schema_in_prompt=False,
                use_case=section_use_case,
            )
        except Exception as exc:
            msg = f"structured LLM call failed: {exc}"
            logger.error(f"{section['name']} {msg}")
            chunk_errors.append(str(exc))
            return []

        # Pydantic instance → list of dicts (or strings for keywords).
        if section["schema_key"] == "keywords":
            return list(getattr(result, "items", []))
        return [item.model_dump(mode="json") for item in getattr(result, "items", [])]

    chunk_results: list[list[Any]] = await asyncio.gather(
        *[_extract_chunk(c) for c in chunks]
    )

    # Flatten for the markdown artifact (legacy view); attach per-page
    # provenance for the KG write below.
    items: list[Any] = [item for chunk_items in chunk_results for item in chunk_items]

    markdown = _render_section_markdown(section, items)

    # Dual write: KG rows (with per-page provenance) + markdown artifact.
    #
    # KG rows (KnowledgeEntity + KnowledgeClaim) are the queryable substrate
    # for cross-doc search and the 0.2.x KG layer (#728). Markdown artifacts
    # stay alongside as the human-readable / debug view (Daniel: "keep
    # markdown so we can debug as a user more easily"). Both writes are
    # idempotent on canonical_name+entity_type for entities; claims always
    # append (provenance trail).
    if container and library_path and any(chunk_results):
        try:
            db = db_manager.get_database(library_path)
            for page_idx, (chunk_text, chunk_items, page_doc_id) in enumerate(
                zip(chunks, chunk_results, page_doc_ids)
            ):
                if not chunk_items:
                    continue
                page_label = f"Page {page_idx + 1}" if len(chunks) > 1 else None
                excerpt = chunk_text[:500] if chunk_text else None
                # Save to PAGE doc when we have its id (0.0.2: per-page KG
                # search). Fall back to container only when records flow
                # didn't carry doc_ids — preserves legacy behaviour for
                # non-aggregate workflows.
                target_doc_id = page_doc_id or container.id
                _write_kg_rows(
                    db, section, chunk_items, target_doc_id,
                    page_label=page_label, source_excerpt=excerpt,
                )
        except Exception as exc:
            logger.error(f"{section['name']}: KG write failed: {exc}")

    # Save artifact(s).
    #
    # Per-page records flow: save ONE artifact per page doc. This is the
    # source of truth — the per-page cache check above looks here, and
    # the inspector renders the artifact alongside the page. Page cleanup
    # then writes <key>_clean artifacts on top.
    #
    # Legacy / no-records flow: save ONE artifact on the container.
    if container and library_path:
        try:
            db = db_manager.get_database(library_path)
            if is_per_page:
                for chunk_text, chunk_items, page_doc_id in zip(
                    chunks, chunk_results, page_doc_ids
                ):
                    if not page_doc_id:
                        continue
                    page_md = _render_section_markdown(section, chunk_items)
                    page_artifact = Artifact(
                        document_id=page_doc_id,
                        artifact_type=section["artifact"],
                        content=page_md,
                        data={"items": chunk_items} if chunk_items else None,
                        provider=getattr(llm_config, "provider", None),
                        model=getattr(llm_config, "model", None),
                        run_id=state.get("task_id"),
                    )
                    db.save(page_artifact)
                # Bump container updated_at so the folder inspector refreshes.
                container.updated_at = datetime.now()
                db.save(container)
                logger.info(
                    f"{section['name']}: saved {section['artifact']} on "
                    f"{sum(1 for p in page_doc_ids if p)} page docs "
                    f"(records-driven flow)"
                )
            else:
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
                container.updated_at = datetime.now()
                db.save(container)
                logger.info(
                    f"{section['name']}: saved {section['artifact']} artifact "
                    f"{artifact.id} on container {container.id}"
                )
        except Exception as exc:
            logger.error(f"{section['name']}: artifact save failed: {exc}")

    # If we got NO items AND every chunk failed, surface the upstream
    # error in the result so the workflow runner / Activity tab show
    # "Dates: LLM call failed: 403 quota exceeded" instead of a silent
    # "_No entries found._". Pick the most informative error string —
    # quota / auth / rate-limit messages from cloud providers contain
    # the URL the user needs.
    result: dict[str, Any] = {"text": markdown, "value": items, "cached": False}
    if not items and chunk_errors:
        # Prefer a quota / auth / rate-limit message if we saw one; they
        # contain actionable URLs and are the most common silent failure.
        actionable = next(
            (e for e in chunk_errors
             if any(k in e.lower() for k in ("quota", "limit", "401", "403", "402"))),
            chunk_errors[0],
        )
        result["error"] = (
            f"{section['display']}: {len(chunk_errors)}/{len(chunks)} "
            f"LLM calls failed — {actionable}"
        )
    return result


def _write_kg_rows(
    db,
    section: dict[str, Any],
    items: list[Any],
    container_id: str,
    page_label: str | None = None,
    source_excerpt: str | None = None,
) -> None:
    """Persist extractor items as KnowledgeEntity + KnowledgeClaim rows.

    Sections with ``entity_type`` set produce one entity per item (upsert
    by canonical_name) plus one claim linking the entity to the source
    document. Sections with ``entity_type=None`` (dates) produce claims
    only — the date itself is the claim, no canonical entity to dedup.

    ``page_label`` and ``source_excerpt`` carry per-page provenance — set
    when the caller is processing per-page chunks via ``_split_into_pages``.
    Both fields land on the ``KnowledgeClaim`` so cross-doc views can
    answer "which page of which document mentions this entity?"
    """
    from fichero.knowledge_models import ClaimType, EpistemicStatus
    from fichero.workflows.tools._entity_writer import upsert_entity, save_claim

    entity_type = section.get("entity_type")
    page_excerpt = source_excerpt  # rename for clarity below

    # First-person → third-person rewrite (#963).
    # When the container document carries source_metadata.authors, we
    # substitute the first author's name (or surname) for first-person
    # pronouns in extractor-emitted verbs / objects so claims read as
    # attributed third-person prose. Without an author we leave the
    # text alone (better than guessing). This is a stop-gap until the
    # bibliography pipeline ships richer speaker-role tagging via #924.
    from fichero.models import Document as DocumentModel
    container_doc = db.get(DocumentModel, container_id)
    author_label: str | None = None
    if container_doc and container_doc.source_metadata:
        authors = container_doc.source_metadata.get("authors") or []
        if authors:
            first = str(authors[0] or "").strip()
            if first:
                # Use surname when "Family, Given" or "Given Family"
                # — both common citation styles. Last token is a safe
                # surname guess for English/Spanish names; for compound
                # surnames (de la Cruz, García Márquez) we accept the
                # imperfect form. Better than nothing.
                if "," in first:
                    author_label = first.split(",", 1)[0].strip()
                else:
                    author_label = first.split()[-1] if first.split() else first

    def _rewrite_first_person(text: str) -> str:
        """Replace 'me' / 'my' / 'our' / 'us' / 'I' with the author's
        label when known, else return the text unchanged. Case-
        insensitive whole-word match so 'message' / 'imagine' don't
        get clobbered. (#963)"""
        if not text or not author_label:
            return text
        import re as _re
        # Build replacements in length-descending order so "myself"
        # matches before "my".
        replacements = [
            (r"\bmyself\b", author_label),
            (r"\bourselves\b", f"{author_label} and colleagues"),
            (r"\bmy\b", f"{author_label}'s"),
            (r"\bour\b", f"{author_label}'s"),
            (r"\bme\b", author_label),
            (r"\bus\b", author_label),
            (r"\bI\b", author_label),
            (r"\bwe\b", f"{author_label} and colleagues"),
        ]
        out = text
        for pattern, replacement in replacements:
            out = _re.sub(pattern, replacement, out, flags=_re.IGNORECASE)
        return out

    # Within-call dedup (#896): when a page gets sub-chunked at the
    # 3000-char boundary (#extract_chunk), each sub-chunk's LLM call
    # may independently emit the same entity, and a single LLM call
    # often emits one item per textual occurrence rather than folding
    # variants into alternative_spellings. The result is N near-
    # duplicate items for one underlying fact on one page. Collapse
    # them here BEFORE any DB write so we don't get six "Davidson is
    # an alternative spelling of Deibinson" claims for one page-1
    # mention pattern.
    #
    # Dedup key: (canonical lowered, normalized predicate). Date
    # sections key on (normalized date, predicate). Preserves the
    # first item's source_text + alternative_spellings; later
    # duplicates fold their spellings into the first.
    def _norm(s: Any) -> str:
        return " ".join(str(s or "").lower().split())

    def _dedup_key(item: dict) -> tuple[str, str]:
        canonical = (
            item.get("name")
            or item.get("event")
            or item.get("date")
            or item.get("nombre")
            or item.get("evento")
            or item.get("fecha")
            or ""
        )
        if entity_type is None:
            canonical = item.get("date_normalized") or canonical
        predicate = f"{item.get('verb') or ''} {item.get('object') or ''}".strip()
        legacy = item.get("context") or item.get("contexto") or ""
        return (_norm(canonical), _norm(predicate or legacy))

    deduped: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    for raw_item in items:
        if not isinstance(raw_item, dict):
            # Keywords come through as bare strings — preserve uniqueness
            # by the string itself.
            key = ("", _norm(raw_item))
            if key in seen:
                continue
            seen[key] = {"name": str(raw_item)}
            deduped.append(seen[key])
            continue
        key = _dedup_key(raw_item)
        if not key[0] and not key[1]:
            # Nothing to dedup against — pass through.
            deduped.append(raw_item)
            continue
        if key in seen:
            # Fold alternative spellings from the duplicate into the
            # first occurrence so we don't lose surface-form evidence.
            existing = seen[key]
            existing_aliases = set(existing.get("alternative_spellings") or [])
            dup_aliases = set(raw_item.get("alternative_spellings") or [])
            merged = existing_aliases | dup_aliases
            # Also fold the duplicate's name itself when it differs in
            # casing/accent — useful surface-form evidence.
            existing_name = existing.get("name")
            dup_name = raw_item.get("name")
            if existing_name and dup_name and _norm(existing_name) == _norm(dup_name) and existing_name != dup_name:
                merged.add(dup_name)
            if merged:
                existing["alternative_spellings"] = sorted(merged)
            continue
        seen[key] = raw_item
        deduped.append(raw_item)

    if len(deduped) < len(items):
        logger.info(
            f"_write_kg_rows: deduped {len(items)} → {len(deduped)} items "
            f"for {section.get('name')} on {container_id}"
        )
    items = deduped

    def _coerce_enum(raw: Any, enum_cls):
        """Map an LLM-emitted string to enum_cls; None for unknowns.

        Grammar-constrained decoding usually keeps values inside the
        valid set, but legacy artifacts and unconstrained providers can
        emit anything. None → save_claim leaves the model default.
        """
        if not raw:
            return None
        try:
            return enum_cls(str(raw).strip().lower())
        except ValueError:
            return None

    for item in items:
        if not isinstance(item, dict):
            # Keywords come through as bare strings — wrap minimally.
            item = {"name": str(item)}

        # Field names vary per section: name (most), event (events),
        # date (dates). Try English first, then legacy Spanish keys, so
        # both new and old artifacts produce a sensible canonical_name.
        canonical = (
            item.get("name")
            or item.get("event")
            or item.get("date")
            or item.get("nombre")
            or item.get("evento")
            or item.get("fecha")
            or ""
        )
        # SVO predicate (new schema). `verb` + `object` compose the
        # claim text as a real sentence; the legacy `context` is still
        # accepted for any in-flight cache hits or human-authored items
        # so deletions are graceful.
        verb = (item.get("verb") or "").strip()
        obj = (item.get("object") or "").strip()
        legacy_context = (
            item.get("context") or item.get("contexto") or ""
        ).strip()
        # First-person rewrite — when the doc has a known author and the
        # extractor surfaced "me / my / our" (typical for academic
        # prefaces describing the author's own life), substitute the
        # author's name so the claim reads as attributed third-person.
        # No-op when author_label is None. (#963)
        verb = _rewrite_first_person(verb)
        obj = _rewrite_first_person(obj)
        legacy_context = _rewrite_first_person(legacy_context)
        predicate = (
            f"{verb} {obj}".strip() if (verb or obj) else legacy_context
        )

        # Verbatim source text the LLM lifted from the input — the
        # narrowest, most useful excerpt for showing + highlighting in
        # the source PDF. Falls back to the predicate (legacy items) and
        # then the whole page chunk so older artifacts still surface
        # something rather than going blank.
        source_text = (item.get("source_text") or "").strip()
        excerpt = source_text or predicate or page_excerpt or None

        # Sub-page anchor (#913): when source_text appears verbatim
        # inside the page chunk, record the character offset so the
        # inspector can navigate to the exact span instead of just
        # the page. Cheap substring search — bbox lookup (PyMuPDF)
        # is deferred to a follow-up since it requires the PDF file
        # on disk + page number.
        char_start: int | None = None
        char_end: int | None = None
        if source_text and page_excerpt:
            idx = page_excerpt.find(source_text)
            if idx >= 0:
                char_start = idx
                char_end = idx + len(source_text)

        meta: dict[str, Any] = {}
        if verb:
            meta["verb"] = verb
        if obj:
            meta["object"] = obj
        if source_text:
            # Persist the verbatim quote separately from source_excerpt
            # so the UI can distinguish "LLM-quoted span" from
            # "fallback page chunk" and drive search-highlight.
            meta["source_text"] = source_text

        # Two-axis classification on every claim:
        #   epistemic_status — how firmly asserted (tentative/confirmed/rejected)
        #   claim_type        — ontological status (fact/analysis/.../theory)
        # Both are declared fields on KnowledgeClaim, so values survive
        # model_dump(). Unknown LLM strings → None → model default.
        epistemic = _coerce_enum(item.get("epistemic_status"), EpistemicStatus)
        ctype = _coerce_enum(item.get("claim_type"), ClaimType)

        # Temporal scope (#904) — empty strings become None so the
        # KnowledgeClaim field stays NULL when the LLM doesn't date it.
        t_start = (item.get("time_start") or "").strip() or None
        t_end = (item.get("time_end") or "").strip() or None
        # Toulmin (#907) — populated by the LLM only for analytic
        # claim_types; fact claims emit empty strings which we drop.
        grounds_val = (item.get("grounds") or "").strip() or None
        warrant_val = (item.get("warrant") or "").strip() or None
        if grounds_val or warrant_val:
            meta.setdefault("toulmin", {})
            if grounds_val:
                meta["toulmin"]["grounds"] = grounds_val
            if warrant_val:
                meta["toulmin"]["warrant"] = warrant_val

        if entity_type is None:
            # Date-style section: claim only. Normalized date in metadata.
            # Claim text composes as "{date}: {verb} {object}." so it
            # reads naturally with the date as implicit subject.
            date_text = item.get("date") or item.get("fecha") or canonical
            normalized = (
                item.get("date_normalized")
                or item.get("fecha_normalizada")
                or ""
            )
            stem = normalized or date_text
            claim_text = (
                f"{stem}: {predicate}." if predicate else stem
            )
            meta["date_text"] = date_text
            meta["date_normalized"] = normalized
            meta["subject"] = stem
            save_claim(
                db,
                text=claim_text,
                source_document_id=container_id,
                source_excerpt=excerpt,
                source_page_label=page_label,
                source_char_start=char_start,
                source_char_end=char_end,
                claim_type=ctype or ClaimType.fact,
                metadata=meta,
                epistemic_status=epistemic,
                time_start=t_start,
                time_end=t_end,
            )
            continue

        # Entity-bearing section.
        if not canonical:
            continue
        aliases = (
            item.get("alternative_spellings")
            or item.get("ortografias_alternativas")
            or []
        )
        meta["subject"] = canonical
        # Claim text reads as a real sentence: "{name} {verb} {object}.".
        # When verb+object are missing (legacy path), fall back to the
        # older "{name}: {context}" shape rather than producing a noun
        # fragment.
        if verb or obj:
            claim_text = f"{canonical} {predicate}.".strip()
        elif legacy_context:
            claim_text = f"{canonical}: {legacy_context}"
        else:
            claim_text = canonical
        entity_id = upsert_entity(
            db,
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=aliases if isinstance(aliases, list) else [],
            # The entity's curated description used to be the raw
            # context; with SVO it's the full predicate so users still
            # see a useful blurb in the inspector.
            description=predicate or None,
        )
        save_claim(
            db,
            text=claim_text,
            source_document_id=container_id,
            entity_ids=[entity_id],
            source_excerpt=excerpt,
            source_page_label=page_label,
            source_char_start=char_start,
            source_char_end=char_end,
            claim_type=ctype or ClaimType.fact,
            metadata=meta,
            epistemic_status=epistemic,
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
        # Expose the prompt for transparency. The JSON-schema portion is a
        # parser contract — editing the prompt is allowed but breaking the
        # schema_key or shape will cause silent parse failures.
        default_prompt=_build_section_prompt(section, "Spanish"),
        sort_order=10 + _SECTIONS.index(section),
    )(_tool)

    return _tool


# Exported so __init__.py importing this module triggers registration.
EXTRACTORS = {section["name"]: _make_registered(section) for section in _SECTIONS}
