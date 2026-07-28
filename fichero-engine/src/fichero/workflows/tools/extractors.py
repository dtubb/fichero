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
from fichero.models.knowledge import EntityType

import asyncio
import json
import logging
import re as _re
import unicodedata
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from fichero.db import db_manager
from fichero.kg._common import parse_kwarg_repr
from fichero.llm import (
    LLMConfig,
    ProviderQuotaError,
    chat_structured_with_fallback,
)
from fichero.models import Artifact
from fichero.workflows.tools._workflow_change_emit import emit_workflow_artifact_changes
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.catalogue import _resolve_write_target
from fichero.workflows.tools.llm_base import (
    ArtifactLookupError,
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

_NER_CONFIG = {
    "ner_provider": {
        "type": "string",
        "default": "spacy",
        "description": "NER hint provider: spacy, llm, or transformers",
    },
    "ner_model": {
        "type": "string",
        "default": "",
        "description": "Optional NER backend model (e.g. en_core_web_sm, en_core_web_trf)",
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
            "Always include prepositions in multi-word verbs. "
            "If a mention is obscured, do not guess it; preserve any "
            "[ilegible] / [uncertain] markers exactly as written. "
            "Examples: name='Eugenio Córdoba', verb='served as', "
            "object='the alcalde of Popayán'; or verb='entered into', "
            "object='partnership with the mining company'. Aliases are spelling "
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
            "List every place — cities, towns, regions, countries, "
            "neighbourhoods, addresses, rivers, mines, estates. This "
            "includes geographic and land-use CATEGORIES, not just "
            "proper names: 'agricultural zones', 'mining districts', "
            "'territories', 'the highlands' all belong here. If a term "
            "denotes a location or land area — even a generic one — it "
            "is a place, NOT a keyword/concept. 'name' in Title Case "
            "(preserve original spelling and accents). "
            "'alternative_spellings' = spelling variants in the text. "
            "Predicate split into 'verb' + 'object' so the claim text "
            "composes as 'f'{name} {verb} {object}.' — name is the "
            "implicit subject. Always include prepositions in multi-word verbs. "
            "Examples: name='Chocó', verb='is', object='the region where artisanal mining occurs'; "
            "or name='Atrato', verb='drains', object='westward to the Caribbean'; "
            "or name='Popayán', verb='served as', object='the center of colonial mining operations'."
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
            "Predicate split into 'verb' + 'object'. Always include prepositions "
            "in multi-word verbs. Preserve any [ilegible] / [uncertain] "
            "markers exactly as written. Examples: "
            "name='Imprenta Oficial', verb='published', "
            "object='the official gazette of the Republic'; "
            "or name='Banking Authority', verb='entered into', object='agreements with the Crown'; "
            "or name='Ministry of Mines', verb='funded exploration', object='in the Atrato basin'."
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
            "composes as 'f'{date}: {verb} {object}.' Always include prepositions "
            "in multi-word verbs. Examples: "
            "verb='records', object='the filing of a mining petition by the heirs'; "
            "or verb='was filed', object='a petition to enter into partnerships'; "
            "or verb='marks', object='the transfer of ownership to the Crown'."
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
            "List significant events — any OCCURRENCE the text records. "
            "This includes unnamed/generic occurrences: 'accident', "
            "'flood', 'death', 'fire', 'strike' are events, NOT "
            "keywords/concepts. If a term denotes something that "
            "happened (an incident, decision, hearing, death, "
            "transaction, petition, ruling, transfer), it is an event. "
            "'event' is a noun phrase naming the occurrence — Title Case "
            "for named events ('Mining Boom', 'Petition to the Court'), "
            "or the bare noun for generic ones ('Accident', 'Flood'). "
            "'date' is YYYY-MM-DD (or YYYY-MM / YYYY) when stated, else "
            "null. Predicate split into 'verb' + 'object' (past tense). "
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
        "name": "citation_usage_extract",
        "display": "Extract Citation Usage",
        "artifact": "citation_usages",
        "entity_type": None,
        "icon": "quote.bubble",
        "color": "teal",
        "schema_key": "citation_usages",
        "item_shape": (
            '{"marker": "...", "cited_work": "...", '
            '"stance": "cites|supports|extends_reading|contests_reading|'
            'critiques|defends", "claim_text": "...", '
            '"excerpt": "...", "char_start": 0, "char_end": 12, '
            '"confidence": 0.8}'
        ),
        "instruction": (
            "Detect every in-text citation marker in the document body "
            "(Author-Year, numeric bracket references like [12], and "
            "footnote/endnote reference markers). For each marker, infer "
            "which cited work it points to, summarize exactly HOW the "
            "author uses that source, and classify the stance. "
            "'marker' is the literal citation marker as written. "
            "'cited_work' is the best author/year/title label you can "
            "infer from the surrounding text. 'stance' must be one of: "
            "cites, supports, extends_reading, contests_reading, critiques, "
            "defends. 'claim_text' is a short statement of the author's "
            "use of the source. 'excerpt' is the shortest surrounding "
            "sentence or paragraph containing the citation marker. "
            "'char_start' and 'char_end' are offsets for the marker inside "
            "the provided text chunk when you can determine them; use null "
            "when unsure. Skip bibliography entries themselves unless the "
            "body text discusses how a source is being used."
        ),
    },
    {
        "name": "hermeneutics_extract",
        "display": "Extract Interpretations",
        "artifact": "hermeneutics",
        "entity_type": EntityType.concept,
        "icon": "text.quote",
        "color": "purple",
        "schema_key": "hermeneutics",
        "item_shape": '{"name": "...", "verb": "...", "object": "..."}',
        "instruction": (
            "Extract only interpretive claims the document itself supports. "
            "Name the interpreted theme, practice, or concept; split the "
            "interpretation into verb and object; include the shortest "
            "supporting source_text. Do not turn unstated speculation into fact."
        ),
    },
    {
        "name": "quotes_extract",
        "display": "Extract Quotes",
        "artifact": "quotes",
        "entity_type": EntityType.person,
        "icon": "text.quote",
        "color": "purple",
        "schema_key": "quotes",
        "allow_null_subject": True,
        "item_shape": (
            '{"name": "Speaker name or null", '
            '"verb": "said|argued|wrote|testified", '
            '"object": "verbatim quote text", '
            '"source_text": "surrounding sentence"}'
        ),
        "instruction": (
            "Extract every DIRECT QUOTATION — text the source presents as verbatim "
            "words spoken or written by a specific person. "
            "'name' = the speaker's name as written in the text (preserve original "
            "spelling and accents), or null when no speaker is identified. "
            "'verb' = the attribution verb (said, argued, wrote, testified, reported, "
            "declared, stated, asked). "
            "'object' = the verbatim quoted text exactly as it appears in the source "
            "— preserve original punctuation, spelling, accents, and any "
            "[ilegible] / [uncertain] markers exactly as written. Do NOT "
            "paraphrase or summarise the quote. "
            "'source_text' = the shortest surrounding sentence or phrase that "
            "contains both the quote and its attribution, to anchor it in context. "
            "ONLY extract text that is clearly a direct quotation (enclosed in "
            "quotation marks or attributed with a speech verb). "
            "Skip paraphrases, indirect speech, and the author's own narrative voice."
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
            "List the 5-8 MOST SALIENT, distinctive keywords for "
            "ABSTRACT ideas only — themes, subjects, time periods, "
            "ideologies, theoretical constructs (e.g. 'gender', 'food "
            "insecurity', 'land reform'). "
            "Do NOT put places, events, people, or organizations here: "
            "if a term names a location (even a land-use category like "
            "'agricultural zones') it belongs in places; if it names an "
            "occurrence (like 'accident' or 'flood') it belongs in "
            "events. Keywords are concepts, not concrete entities. "
            "Pick the concepts a reader would TAG this passage with — "
            "skip generic words ('work', 'cash', 'children', "
            "'education') that merely appear but don't characterise it. "
            "Prefer specific over generic. Order most salient first. "
            "Return a flat array of short strings (no objects)."
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
        "subject — do NOT repeat it. Always include prepositions in "
        "multi-word verbs. Examples: 'is', 'was', 'served as', 'wrote', "
        "'founded', 'is located in', 'entered into', 'funded trips to', "
        "'was appointed as', 'transferred to'."
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


class _SectionCitationUsage(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        if isinstance(data, dict):
            data.setdefault("confidence", 0.5)
            data.setdefault("char_start", None)
            data.setdefault("char_end", None)
        return data

    marker: str = Field(
        description="Literal in-text citation marker as written, e.g. '(Smith 1999)' or '[12]'."
    )
    cited_work: str = Field(
        description="Best author/year/title label for the cited work."
    )
    stance: str = Field(
        description=(
            "How the author uses the cited work: cites, supports, "
            "extends_reading, contests_reading, critiques, or defends."
        )
    )
    claim_text: str = Field(
        description="Short statement of how the author uses the cited work."
    )
    excerpt: str = Field(
        description=(
            "Shortest surrounding sentence or paragraph containing the "
            "citation marker, copied verbatim."
        )
    )
    char_start: int | None = Field(
        default=None,
        description="Start offset of marker in this text chunk when known.",
    )
    char_end: int | None = Field(
        default=None,
        description="End offset of marker in this text chunk when known.",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class _SectionQuote(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        return _fill_required_defaults(data)

    name: str | None = Field(
        default=None,
        description=(
            "Speaker's name as written in the text (preserve original spelling "
            "and accents), or null when no speaker is identified in the passage."
        ),
    )
    verb: str = _SVO_VERB_FIELD
    object: str = _SVO_OBJECT_FIELD
    epistemic_status: str = _EPISTEMIC_FIELD
    claim_type: str = _CLAIM_TYPE_FIELD
    source_text: str = _SOURCE_TEXT_FIELD
    time_start: str = _TIME_START_FIELD
    time_end: str = _TIME_END_FIELD


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
    "citation_usages": _make_section_schema(_SectionCitationUsage, "citation_usages"),
    "hermeneutics": _make_section_schema(_SectionLegalReference, "hermeneutics"),
    "quotes": _make_section_schema(_SectionQuote, "quotes"),
}


# Runaway-cap backstop (#1051). The instruction asks for 5-8 salient
# keywords; this trims a model that ignores the ceiling and dumps every
# abstract noun. Keeps the first N — the instruction asks for
# most-salient-first ordering.
_KEYWORDS_MAX = 12


class _KeywordsResult(BaseModel):
    """Keywords are flat strings, not objects."""

    items: list[str] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def _cap_runaway(cls, v: list[str]) -> list[str]:
        return v[:_KEYWORDS_MAX]


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
        f"  original spelling, accents, punctuation, and any "
        f"  [ilegible] / [uncertain] markers exactly as written. Do NOT "
        f"  paraphrase, translate, resolve, or delete this field.\n"
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
    r"""Strip wrapping that gets between us and the JSON object.

    Handles three common shapes that frontier cloud models (hit via the
    $large guardrail fallback, #838) emit instead of bare JSON:

      1. Triple-backtick code fences (```json ... ```)
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


# Function-word / connector tokens the LLM sometimes leaks as a
# stand-alone "description" when it can't compose a proper predicate
# (e.g. verb="called", object="" → predicate="called"). Compared
# against the case-folded predicate, AFTER splitting on whitespace —
# matching any token here is fine since a 1-word predicate of one of
# these is by definition degenerate. (#1016)
_DEGENERATE_DESCRIPTION_TOKENS: frozenset[str] = frozenset(
    {
        "a", "an", "the",
        "of", "in", "at", "on", "to", "for", "from", "with", "by",
        "as", "is", "was", "be", "been", "being", "are", "were",
        "and", "or", "but",
        "called", "named", "noted", "known", "said", "mentioned",
    }
)


def _sanitize_entity_description(
    text: str | None, canonical_name: str
) -> str | None:
    """Return a clean entity description or ``None`` when degenerate.

    The catalogue/extract path stores the SVO predicate as the entity's
    description so the inspector shows a useful blurb. When the LLM
    can't compose a real predicate it sometimes leaks adjacent function
    words ("called", "noted", "a neighbor's") which then surface as the
    entity description. Empty is a better signal than misleading
    content — reject those at write time. (#1016)

    Rejected cases:
    - empty / whitespace-only
    - shorter than 3 words
    - all tokens are function/connector words from
      ``_DEGENERATE_DESCRIPTION_TOKENS``
    - the description is a substring of the canonical name itself
      (case-insensitive, after stripping punctuation), which means
      we're storing the name as the description — not informative
    """
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None

    tokens = cleaned.split()
    if len(tokens) < 3:
        return None

    folded = [t.casefold().strip(".,;:!?'\"()[]") for t in tokens]
    if all(t in _DEGENERATE_DESCRIPTION_TOKENS or not t for t in folded):
        return None

    canonical_folded = (canonical_name or "").casefold().strip()
    if canonical_folded and cleaned.casefold() in canonical_folded:
        return None

    return cleaned


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

    from fichero.llm.lang_detect import configured_primary_language, resolve_output_language
    output_language = resolve_output_language(
        inputs.get("output_language"),
        text,
        default="English",
        primary_language=configured_primary_language(),
    )
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    # Use the write-target helper so single-file selections still get
    # KG entities/claims persisted on the file itself (#1105).
    container = _resolve_write_target(selected_doc_ids, library_path)

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
            try:
                cached = find_existing_artifact(
                    document_id=pid,
                    file_path=None,
                    artifact_type=section["artifact"],
                    library_path=library_path,
                    provider=getattr(llm_config, "provider", None),
                    model=getattr(llm_config, "model", None),
                )
            except ArtifactLookupError as exc:
                # Cache read FAILED — we do not know if a page artifact exists.
                # Don't treat that as a hit OR a clean miss: log loud and force
                # the full re-extract path (visible re-run, never a silent
                # cache decision on an unknown). (#2511)
                logger.error(
                    "%s: per-page cache check FAILED for page %s — re-extracting "
                    "all pages (not assuming cache state): %s",
                    section["name"],
                    pid,
                    exc,
                )
                every_page_cached = False
                break
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
        try:
            cached = find_existing_artifact(
                document_id=container.id,
                file_path=None,
                artifact_type=section["artifact"],
                library_path=library_path,
                provider=getattr(llm_config, "provider", None),
                model=getattr(llm_config, "model", None),
            )
        except ArtifactLookupError as exc:
            # Cache read FAILED — re-run rather than silently treat as a miss
            # (which would hide the fault) or a hit (which we cannot prove).
            # (#2511)
            logger.error(
                "%s: cache check FAILED for %s — re-extracting (not assuming "
                "cache state): %s",
                section["name"],
                container.id,
                exc,
            )
            cached = None
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

    # NER pre-pass (#899 Phase C). For people / places /
    # organizations / events sections we run a selectable NER backend
    # first and pass the detected mention list as a hint in the LLM
    # prompt. Two wins:
    # 1. Sub-chunk dedup: even when we split a long page at 3000 chars,
    #    both sub-chunks see the same span list, so they produce one
    #    canonical entity name across them (down with the #896
    #    Davidson × 6 pattern). The provider runs on the full chunk
    #    before splitting.
    # 2. Boundary consistency: the LLM trusts the provider's PERSON /
    #    ORG / GPE / EVENT calls — no more "Eugenio Córdoba" vs "Mr
    #    Córdoba" drift between calls.
    # Sections without a matching entity label (dates, keywords, etc.)
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
            from fichero.workflows.ner.providers import get_ner_provider

            ner_provider_name = inputs.get("ner_provider", "spacy")
            ner_model_name = inputs.get("ner_model") or None
            ner_provider = get_ner_provider(ner_provider_name, ner_model_name)
            all_spans = await ner_provider.extract(
                text,
                state=state,
                llm_config=llm_config,
                inputs=inputs,
            )
            relevant = [s for s in all_spans if s.type == spacy_target]
            for span in relevant:
                if span.aliases:
                    spacy_hint_lines.append(
                        f"- {span.name} (aliases: {', '.join(span.aliases)})"
                    )
                else:
                    spacy_hint_lines.append(f"- {span.name}")
        except Exception as exc:
            # Don't take down the catalogue if spaCy is unhealthy.
            logger.warning("%s: NER pre-pass failed: %s", section["name"], exc)

    async def _extract_chunk(chunk_text: str, chunk_idx: int = 0) -> list[Any]:
        # Split a single page into sub-chunks if it exceeds the model's
        # context budget. Each sub-chunk gets its own LLM call; results
        # concatenate.
        #
        # Overlap context (#971): prepend tail of previous chunk to provide
        # entity context when they span page boundaries. Example: if "Eugenio
        # Córdoba" spans pages, page 2's extraction will include "...Eugenio"
        # from the previous chunk, giving the LLM full context. This helps
        # when NER mentions span pages or quotes continue across boundaries.
        _OVERLAP_CHARS = 200
        extraction_text = chunk_text
        if chunk_idx > 0 and chunk_idx < len(chunks):
            prev_chunk = chunks[chunk_idx - 1]
            overlap_tail = prev_chunk[-_OVERLAP_CHARS:] if len(prev_chunk) > _OVERLAP_CHARS else prev_chunk
            if overlap_tail:
                extraction_text = overlap_tail + " " + chunk_text

        if len(extraction_text) > _MAX_CHUNK_CHARS:
            sub_chunks = []
            for start in range(0, len(extraction_text), _MAX_CHUNK_CHARS):
                sub_chunks.append(extraction_text[start:start + _MAX_CHUNK_CHARS])
            sub_results = await asyncio.gather(
                *[_extract_one(s) for s in sub_chunks]
            )
            return [item for sub in sub_results for item in sub]
        return await _extract_one(extraction_text)

    # Track per-chunk LLM errors so we can distinguish "the document
    # genuinely has no entities" from "every LLM call hit a 403 / timeout
    # / parse failure". Without this, quota / auth / model-down errors
    # silently render as "_No entries found._" and the user has no clue
    # the cloud provider is rejecting calls.
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
                permissive_guardrails=True,
            )
        except ProviderQuotaError:
            raise
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
        *[_extract_chunk(c, idx) for idx, c in enumerate(chunks)]
    )

    # Flatten for the markdown artifact (legacy view); attach per-page
    # provenance for the KG write below.
    items: list[Any] = [item for chunk_items in chunk_results for item in chunk_items]

    markdown = _render_section_markdown(section, items)
    created_artifact_ids: list[str] = []
    artifact_document_ids: set[str] = set()

    # Dual write: KG rows (with per-page provenance) + markdown artifact.
    #
    # KG rows (KnowledgeEntity + KnowledgeClaim) are the queryable substrate
    # for cross-doc search and the 0.2.x KG layer (#728). Markdown artifacts
    # stay alongside as the human-readable / debug view. Both writes are
    # idempotent on canonical_name+entity_type for entities; claims always
    # append (provenance trail).
    if container and library_path and any(chunk_results):
        try:
            db = db_manager.get_database(library_path)
            for page_idx, (chunk_text, chunk_items, page_doc_id) in enumerate(
                zip(chunks, chunk_results, page_doc_ids)
            ):
                page_label = f"Page {page_idx + 1}" if len(chunks) > 1 else None
                if not chunk_items:
                    # #1003: a page producing zero items used to be skipped
                    # silently — indistinguishable from "extraction failed".
                    # Log it explicitly so missing pages surface in the
                    # activity log.
                    logger.info(
                        f"_write_kg_rows: {section.get('name')} "
                        f"{page_label or 'whole-doc'} produced 0 items "
                        f"(extraction ran, found nothing) on {container.id}"
                    )
                    continue
                excerpt = chunk_text[:500] if chunk_text else None
                # Save to PAGE doc when we have its id (0.0.2: per-page KG
                # search). Fall back to container only when records flow
                # didn't carry doc_ids — preserves legacy behaviour for
                # non-aggregate workflows.
                target_doc_id = page_doc_id or container.id
                _write_kg_rows(
                    db, section, chunk_items, target_doc_id,
                    page_label=page_label, source_excerpt=excerpt,
                    provider=getattr(llm_config, "provider", None),
                    model=getattr(llm_config, "model", None),
                    # #1114 issue 3 — full chunk text for the event
                    # grounding guard. Drops hallucinated events that
                    # don't appear in the source.
                    grounding_text=chunk_text,
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
                    created_artifact_ids.append(page_artifact.id)
                    artifact_document_ids.add(page_doc_id)
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
                created_artifact_ids.append(artifact.id)
                artifact_document_ids.add(container.id)
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

    if created_artifact_ids and container and library_path:
        emit_workflow_artifact_changes(
            str(db.path.parent),
            artifact_ids=created_artifact_ids,
            document_ids=artifact_document_ids,
        )
    return result


def _normalize_kwarg_repr_fields(item: dict) -> dict:
    """Repair extractor items where the LLM dumped the prompt's
    kwarg-example format ("verb='X', object='Y'") into one field
    instead of returning structured keys.

    Without this, ``verb`` / ``object`` carry the literal repr string,
    which then composes into ``claim.text`` and the entity description
    as raw ``verb='...', object='...'`` text in the UI. (#1030)

    Returns the item unchanged when no field looks like a repr.
    """
    if not isinstance(item, dict):
        return item
    for field in ("object", "verb", "source_text", "context"):
        val = item.get(field)
        if not isinstance(val, str):
            continue
        parsed = parse_kwarg_repr(val)
        if not parsed:
            continue
        fixed = dict(item)
        if parsed.get("verb"):
            fixed["verb"] = parsed["verb"]
        if parsed.get("object"):
            fixed["object"] = parsed["object"]
        # Only adopt a parsed name when the item has no real name.
        if parsed.get("name") and not str(item.get("name") or "").strip():
            fixed["name"] = parsed["name"]
        # The repr lived in source_text/context — that's not a real
        # verbatim quote, drop it so excerpt fallback stays clean.
        if field in ("source_text", "context"):
            fixed[field] = ""
        return fixed
    return item


def _synthesize_svo_fallback(
    canonical: str,
    verb: str,
    obj: str,
    legacy_context: str,
) -> tuple[str, str]:
    """Last-resort SVO synthesis for items where the LLM didn't return
    a verb / object split. (#1113)

    Strategy:
    - If both verb and object are present → return as-is.
    - If only verb is present → object becomes the verb; verb defaults to "is".
    - If only object is present → verb defaults to "is".
    - If neither, but a legacy_context string exists, parse it:
        - "X: Y" or "X — Y" form (subject-leading description) → verb="is",
          object=Y (drop the leading subject).
        - Otherwise → verb="is", object=legacy_context.
    - If everything is empty → ("", "") — caller decides whether to skip.

    The synthesized verb is "is" because every fallback case observed in
    the wild (#1113 mining-doc test) is a descriptive noun phrase
    ("Chocó: the region where artisanal mining occurs"). A heuristic
    smarter than "is" would mis-tense event items and over-fit; "is" is
    grammatical for descriptive items and at worst awkward (never
    wrong) for predicate items.
    """
    v = (verb or "").strip()
    o = (obj or "").strip()
    if v and o:
        return v, o
    if v and not o:
        # Verb without object — promote verb text to object so we don't
        # emit naked "X verbs ." sentences.
        return "is", v
    if o and not v:
        return "is", o
    ctx = (legacy_context or "").strip()
    if not ctx:
        return "", ""
    # "X: Y" or "X — Y" — strip the subject when it matches canonical.
    for sep in (": ", " — ", " - ", "—", "-"):
        if sep in ctx:
            head, _, tail = ctx.partition(sep)
            head_norm = head.strip().lower()
            canon_norm = (canonical or "").strip().lower()
            if head_norm and (head_norm == canon_norm or head_norm in canon_norm or canon_norm in head_norm):
                tail = tail.strip()
                if tail:
                    return "is", tail
            break  # only try the first separator we hit
    return "is", ctx


# #1119 — reverse alias scan
# ---------------------------
# Walk every claim's text + object_phrase + source_excerpt looking for
# canonical_names or aliases of OTHER known entities, and extend the
# claim's entity_ids[] with the matches. This is the deferred piece of
# the #1113 acceptance criteria: "all claims that mention X" queries
# (entity inspector, KG-RAG retrieval, citation following) walk
# entity_ids[], so a claim like "Chocó is part of the Andes region"
# needs to reference both entities — not just the subject.

_MIN_ALIAS_LENGTH = 4
# Common stopwords / pronouns / connectives that occasionally end up
# as entity canonical_names through degenerate extraction. Skip these
# during reverse alias scan to keep false positives down. The
# upstream extractors already reject these patterns at write time;
# this is defense-in-depth.
_ALIAS_SCAN_STOPLIST = frozenset({
    "this", "that", "these", "those", "they", "them", "their",
    "what", "when", "where", "with", "from", "about",
    "esto", "este", "ese", "esa", "aquel", "ellos", "ellas",
})


def _build_alias_index(db) -> list[tuple[str, str]]:
    """Snapshot of every entity's canonical_name + aliases as a sorted
    list of ``(lowercased_name, entity_id)`` pairs.

    Sorted longest-first so a greedy substring scan prefers
    'Chocó department' over 'Chocó'. The pairs list is rebuilt per
    section, not per claim, so the cost is O(entities) once instead
    of O(entities × claims).
    """
    from fichero.models.knowledge import KnowledgeEntity

    pairs: list[tuple[str, str]] = []
    for ent in db.query(KnowledgeEntity):
        if (
            ent.canonical_name
            and len(ent.canonical_name) >= _MIN_ALIAS_LENGTH
            and ent.canonical_name.lower() not in _ALIAS_SCAN_STOPLIST
        ):
            pairs.append((ent.canonical_name.lower(), ent.id))
        for alias in (ent.aliases or []):
            if (
                alias
                and len(alias) >= _MIN_ALIAS_LENGTH
                and alias.lower() not in _ALIAS_SCAN_STOPLIST
            ):
                pairs.append((alias.lower(), ent.id))
    pairs.sort(key=lambda p: -len(p[0]))
    return pairs


def _scan_for_mentioned_entities(
    text: str,
    alias_pairs: list[tuple[str, str]],
    exclude: set[str],
) -> list[str]:
    """Find entity IDs whose canonical_name or aliases appear as
    whole-word matches in ``text`` (case-insensitive). Excludes ids
    already in ``exclude``. Returns a deduped list preserving the
    order entities were discovered.

    Whole-word match via regex ``\\b`` boundaries prevents 'Lima' from
    matching inside 'climate'. Case-insensitive so 'CHOCÓ' in source
    text still finds the 'Chocó' entity.
    """
    if not text:
        return []
    text_lower = text.lower()
    seen = set(exclude)
    found: list[str] = []
    for name_lower, entity_id in alias_pairs:
        if entity_id in seen:
            continue
        pattern = r"\b" + _re.escape(name_lower) + r"\b"
        if _re.search(pattern, text_lower):
            seen.add(entity_id)
            found.append(entity_id)
    return found


# #1114 issue 3 — event grounding guard
# --------------------------------------
# The event-extraction prompt lists 'Accident, Flood, Death, Fire,
# Strike' as exemplars, which leads the LLM to dutifully extract them
# even for documents that don't mention any of them. Real harm: a doc
# about artisanal mining as a way of life produced "Accident" / "Death"
# / "Strike" event entities the source text didn't support.
#
# Defense-in-depth: post-extract validator that requires at least one
# content token of the event's name to appear in the source chunk text.
# Operates on event entities only — locations / persons / organizations
# have stronger LLM grounding because they're concrete named things.

# Stop tokens dropped before grounding match — these are too common to
# carry signal. Bilingual list (corpus is heavily Spanish + English).
_GROUNDING_STOPWORDS = frozenset({
    # English
    "the", "of", "a", "an", "and", "or", "to", "in", "on", "at", "by",
    "for", "with", "from", "as", "is", "was", "were", "be", "been",
    "has", "have", "had", "this", "that", "these", "those",
    # Spanish
    "el", "la", "los", "las", "de", "del", "y", "o", "a", "en",
    "por", "para", "con", "sin", "es", "fue", "son", "este", "esta",
    "ese", "esa", "un", "una", "su", "le", "les",
})


def _event_grounded_in_text(event_name: str, source_text: str | None) -> bool:
    """Return True when at least one content token of the event's name
    appears (case-insensitively, as a substring) in the source text.

    Stopwords are dropped before the check so 'Filing of the Petition'
    requires 'filing' or 'petition' (not 'of', 'the'). Single-word
    events like 'Accident' require that exact word.

    Fail-open cases (return True) — better to keep a borderline item
    than drop a legitimate one:
    - ``source_text`` is None/empty (caller hasn't been updated yet).
    - ``event_name`` is empty / has no content tokens after stopword
      and short-token filtering. Real hallucinations have full
      word-form names ('Accident', 'Mining Boom'); a single-letter
      name like 'E' is degenerate test/error data, not a hallucinated
      content claim — let the upstream extractor validation catch it.

    The strict case (return False): the name has content tokens, the
    source has content, and NONE of the content tokens substring-match
    in the source. That's the hallucination signature this guard
    targets.
    """
    if not source_text:
        return True
    if not event_name:
        return True
    cleaned = "".join(
        c if c.isalnum() or c.isspace() else " " for c in event_name.lower()
    )
    content_tokens = [
        tok for tok in cleaned.split()
        if tok and tok not in _GROUNDING_STOPWORDS and len(tok) > 2
    ]
    if not content_tokens:
        # Degenerate name — no content to ground against. Fail-open;
        # upstream extractor validation handles bad names.
        return True
    src_lower = source_text.lower()
    return any(tok in src_lower for tok in content_tokens)


def _reference_match_labels(reference) -> list[str]:
    """Labels used to resolve an extracted marker to a bibliography row."""
    labels: list[str] = []
    authors = [str(a).strip() for a in (getattr(reference, "authors", None) or [])]
    year = getattr(reference, "year", None)
    title = str(getattr(reference, "title", "") or "").strip()
    first_author = authors[0] if authors else ""
    surname = first_author.split(",", 1)[0].strip() if first_author else ""
    if not surname and first_author:
        surname = first_author.split()[-1]

    for value in (
        title,
        f"{surname} {year}".strip(),
        f"{surname} ({year})".strip(),
        f"{surname}, {year}".strip(", "),
        f"{surname} {year} {title}".strip(),
        getattr(reference, "bibtex", ""),
        getattr(reference, "doi", ""),
    ):
        value = str(value or "").strip()
        if value and value not in labels:
            labels.append(value)
    return labels


def _bibliography_candidates(db, source_document_id: str) -> tuple[dict[str, Any], list[str]]:
    """Return match labels for references cited by this document."""
    from fichero.models.knowledge import Reference, ReferenceProvenance

    linked_reference_ids = {
        link.reference_id
        for link in db.query(ReferenceProvenance, document_id=source_document_id)
    }
    references = [
        ref for ref in db.query(Reference)
        if not linked_reference_ids or ref.id in linked_reference_ids
    ]
    by_label: dict[str, Any] = {}
    labels: list[str] = []
    for reference in references:
        for label in _reference_match_labels(reference):
            by_label[label] = reference
            labels.append(label)
    return by_label, labels


def _normalise_usage_span(
    item: dict[str, Any],
    page_excerpt: str | None,
) -> tuple[int | None, int | None]:
    char_start = item.get("char_start")
    char_end = item.get("char_end")
    try:
        if char_start is not None:
            char_start = int(char_start)
        if char_end is not None:
            char_end = int(char_end)
    except (TypeError, ValueError):
        char_start = None
        char_end = None
    if (
        isinstance(char_start, int)
        and isinstance(char_end, int)
        and char_start >= 0
        and char_end >= char_start
    ):
        return char_start, char_end

    marker = str(item.get("marker") or "").strip()
    if marker and page_excerpt:
        idx = page_excerpt.find(marker)
        if idx >= 0:
            return idx, idx + len(marker)
    return None, None


def _write_citation_usage_rows(
    db,
    items: list[Any],
    container_id: str,
    page_label: str | None = None,
    source_excerpt: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    """Persist body citation usages as DocumentCitation + KnowledgeClaim."""
    from fichero.kg._common import canonical_hermeneutic_predicate, slug_verb
    from fichero.models.knowledge import ClaimType, DocumentCitation, KnowledgeClaim
    from fichero.models import Document as DocumentModel
    from fichero.workflows.tools._entity_writer import save_claim
    from fichero.workflows.tools.llm_prompting import match_to_reference

    label_to_reference, reference_labels = _bibliography_candidates(db, container_id)
    source_doc = db.get(DocumentModel, container_id)
    speaker_name: str | None = None
    if source_doc and source_doc.source_metadata:
        authors = source_doc.source_metadata.get("authors") or []
        if authors:
            speaker_name = str(authors[0] or "").strip() or None

    written = 0
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = _normalize_kwarg_repr_fields(raw_item)
        marker = str(item.get("marker") or "").strip()
        cited_work = str(item.get("cited_work") or "").strip()
        claim_text = str(item.get("claim_text") or "").strip()
        excerpt = str(item.get("excerpt") or "").strip() or source_excerpt
        if not marker and not cited_work:
            continue

        matched_label = match_to_reference(cited_work or marker, reference_labels)
        reference = label_to_reference.get(matched_label or "")
        target_document_id = (
            getattr(reference, "realized_as_document_id", None)
            if reference is not None
            else None
        )
        char_start, char_end = _normalise_usage_span(item, source_excerpt)
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        stance = str(item.get("stance") or "cites").strip() or "cites"
        predicate_canonical = (
            canonical_hermeneutic_predicate(stance)
            or slug_verb(stance)
            or "cites"
        )
        reference_id = getattr(reference, "id", None) if reference is not None else None
        target_label = cited_work or marker
        citation = DocumentCitation(
            source_document_id=container_id,
            target_document_id=target_document_id,
            target_citation_text=target_label,
            page_label=page_label,
            char_start=char_start,
            char_end=char_end,
            confidence=confidence,
            detector="llm-usage",
            metadata={
                "marker": marker,
                "cited_work": cited_work,
                "matched_reference_id": reference_id,
                "matched_reference_label": matched_label,
                "stance": stance,
                "predicate_canonical": predicate_canonical,
                "claim_text": claim_text,
                "excerpt": excerpt,
            },
        )
        db.save(citation)

        claim_id = save_claim(
            db,
            text=claim_text or f"{target_label} is cited.",
            source_document_id=container_id,
            entity_ids=[],
            source_excerpt=excerpt,
            source_page_label=page_label,
            source_char_start=char_start,
            source_char_end=char_end,
            claim_type=ClaimType.interpretation,
            confidence=confidence,
            metadata={
                "citation_id": citation.id,
                "reference_id": reference_id,
                "target_document_id": target_document_id,
                "target_citation_text": target_label,
                "marker": marker,
                "stance": stance,
                "predicate_canonical": predicate_canonical,
                "usage_join": "DocumentCitation.metadata.claim_id",
            },
            subject_canonical=speaker_name,
            predicate_verb=stance,
            object_phrase=target_label,
            svo_subject=speaker_name,
            svo_verb=predicate_canonical,
            svo_object=target_label,
            provider=provider,
            model=model,
            speaker_name=speaker_name,
            confidence_origin="llm",
            claim_recorded_at=(source_doc.metadata or {}).get("date") if source_doc else None,
        )
        if claim_id is not None:
            citation.metadata["claim_id"] = claim_id
            db.save(citation)
            claim = db.get(KnowledgeClaim, claim_id)
            if claim is not None:
                claim.predicate_canonical = predicate_canonical
                db.save(claim)
            written += 1

    logger.info(
        "_write_citation_usage_rows: %s on %s — items_in=%d usages_written=%d",
        page_label or "whole-doc",
        container_id,
        len(items),
        written,
    )


def _write_kg_rows(
    db,
    section: dict[str, Any],
    items: list[Any],
    container_id: str,
    page_label: str | None = None,
    source_excerpt: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    grounding_text: str | None = None,
) -> tuple[list[str], list[str]]:
    """Persist extractor items as KnowledgeEntity + KnowledgeClaim rows.

    Sections with ``entity_type`` set produce one entity per item (upsert
    by canonical_name) plus one claim linking the entity to the source
    document. Sections with ``entity_type=None`` (dates) produce claims
    only — the date itself is the claim, no canonical entity to dedup.

    ``page_label`` and ``source_excerpt`` carry per-page provenance — set
    when the caller is processing per-page chunks via ``_split_into_pages``.
    Both fields land on the ``KnowledgeClaim`` so cross-doc views can
    answer "which page of which document mentions this entity?"

    ``grounding_text`` (#1114 issue 3) — full source chunk text used by
    the event grounding guard to drop event items that aren't supported
    by the source text. Source_excerpt is truncated to 500 chars for
    storage; grounding_text is the full chunk so the check sees the
    whole context. None disables the guard (fail-open).
    """
    if section.get("name") == "citation_usage_extract":
        _write_citation_usage_rows(
            db,
            items,
            container_id,
            page_label=page_label,
            source_excerpt=source_excerpt,
            provider=provider,
            model=model,
        )
        return [], []

    from fichero.models.knowledge import (
        ClaimType,
        EntityType,
        EpistemicStatus,
        KnowledgeClaim,
    )
    from fichero.workflows.tools._entity_writer import upsert_entity, save_claim
    from fichero.kg._common import slug_verb

    entity_type = section.get("entity_type")
    page_excerpt = source_excerpt  # rename for clarity below

    # Build the alias index ONCE per section (#1119). Cheaper than per-claim;
    # rebuilt next section so newly-upserted entities are included for the
    # next batch. Pure-read query — safe to run before the writes start.
    try:
        alias_pairs = _build_alias_index(db)
    except Exception as exc:
        logger.warning("alias index build failed: %s", exc)
        alias_pairs = []

    # Event grounding guard (#1114 issue 3) — drop items whose event
    # name has no content token in the source text. Operates only on
    # event sections; other entity types pass through unchanged.
    if entity_type == EntityType.event and grounding_text:
        grounded: list[Any] = []
        dropped: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                # Pydantic model — convert via model_dump for read-only access
                try:
                    item_data = item.model_dump()
                except Exception:
                    item_data = {}
            else:
                item_data = item
            name = (
                item_data.get("event")
                or item_data.get("name")
                or item_data.get("canonical_name")
                or ""
            ).strip()
            if _event_grounded_in_text(name, grounding_text):
                grounded.append(item)
            else:
                dropped.append(name or "<unnamed>")
        if dropped:
            logger.info(
                "event grounding guard: dropped %d hallucinated event(s) "
                "for %s on %s: %s (#1114 issue 3)",
                len(dropped), section.get("name"), container_id,
                ", ".join(dropped[:5]),
            )
        items = grounded

    # First-person → third-person rewrite (#963).
    # When the container document carries source_metadata.authors, we
    # substitute the first author's name (or surname) for first-person
    # pronouns in extractor-emitted verbs / objects so claims read as
    # attributed third-person prose. Without an author we leave the
    # text alone (better than guessing). This is a stop-gap until the
    # bibliography pipeline ships richer speaker-role tagging via #924.
    from fichero.models import Document as DocumentModel
    container_doc = db.get(DocumentModel, container_id)
    doc_date: str | None = (container_doc.metadata or {}).get("date") if container_doc else None
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
        text = " ".join(str(s or "").split()).strip()
        if not text:
            return ""
        folded = unicodedata.normalize("NFKD", text)
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        return " ".join(folded.casefold().split())

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
    item_cap = section.get("max_items") or section.get("max_items_per_page") or 100
    try:
        item_cap = int(item_cap)
    except (TypeError, ValueError):
        item_cap = 100
    if item_cap > 0 and len(deduped) > item_cap:
        logger.warning(
            "_write_kg_rows: capped %s page %s on %s at %d items (from %d)",
            section.get("name"),
            page_label or "whole-doc",
            container_id,
            item_cap,
            len(deduped),
        )
        deduped = deduped[:item_cap]
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

    # Language detection (#1113): detect from page_excerpt once per
    # call rather than per-item. The lang_detect helper is stdlib-only
    # (no langdetect/fasttext dep) and returns canonical names like
    # "English" / "Spanish"; we lower+truncate to a 2-3 letter code so
    # the field stays compact for SPARQL filters.
    detected_language: str | None = None
    if page_excerpt:
        try:
            from fichero.llm.lang_detect import detect_language as _detect
            full = _detect(page_excerpt[:2000], default="")
            if full:
                detected_language = full[:2].lower()  # "English"→"en", "Spanish"→"sp"
                # Map our canonical names to stable ISO-ish codes.
                _ISO = {"en": "en", "sp": "es", "fr": "fr", "de": "de", "po": "pt", "it": "it"}
                detected_language = _ISO.get(detected_language, detected_language)
        except Exception:
            detected_language = None

    # Provider/model attribution (#1113): combine the LLM provider/model
    # with the static "+heuristic-svo" suffix when our local SVO synthesis
    # filled in verb/object that the LLM didn't return. Honest about the
    # hybrid pipeline so users can audit which model produced what.
    base_model_label = (model or "").strip() or None
    base_provider_label = (provider or "").strip() or None

    # #1003: count what actually lands so a structured log at the end
    # exposes per-page (items_in → entities, claims) — missing pages
    # then surface in the activity log instead of failing silently.
    items_in = len(items)
    entities_written = 0
    claims_written = 0
    written_entity_ids: list[str] = []
    written_claim_ids: list[str] = []
    claims_to_embed: list[KnowledgeClaim] = []
    # #1017 layer 2: collect boundary-invariant violations so silent
    # drops (anchorless items, degenerate descriptions) surface in the
    # activity log instead of just shrinking the items_in→written gap.
    from fichero.workflows.tools.extraction_invariants import (
        claim_item_violations,
        entity_description_violation,
        summarize_violations,
    )
    invariant_violations: list[str] = []

    antecedent: str | None = None
    pronouns = {"he", "she", "it", "they", "él", "ella", "ellos", "ellas"}

    def clean_claim_text(value: Any) -> str:
        text = str(value or "")
        text = text.replace("\\\\r\\\\n", " ").replace("\\\\n", " ").replace("\\\\r", " ")
        text = text.replace('\\\\"', '"')
        text = _re.sub(r"\[deleted:\s*[^\]]*\]", "", text, flags=_re.IGNORECASE)
        return " ".join(text.split())

    for item in items:
        if not isinstance(item, dict):
            # Keywords come through as bare strings — wrap minimally.
            item = {"name": str(item)}

        # Repair items where the LLM echoed the prompt's kwarg example
        # ("verb='X', object='Y'") into a single field. (#1030)
        item = _normalize_kwarg_repr_fields(item)

        invariant_violations.extend(
            claim_item_violations(item, is_date_section=entity_type is None)
        )

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
        if canonical.casefold() in pronouns and antecedent:
            canonical = antecedent
        elif canonical:
            antecedent = canonical
        # SVO predicate (new schema). `verb` + `object` compose the
        # claim text as a real sentence; the legacy `context` is still
        # accepted for any in-flight cache hits or human-authored items
        # so deletions are graceful.
        verb = (item.get("verb") or "").strip()
        obj = (item.get("object") or "").strip()
        legacy_context = (
            item.get("context") or item.get("contexto") or ""
        ).strip()
        verb, obj, legacy_context = map(clean_claim_text, (verb, obj, legacy_context))
        # First-person rewrite — when the doc has a known author and the
        # extractor surfaced "me / my / our" (typical for academic
        # prefaces describing the author's own life), substitute the
        # author's name so the claim reads as attributed third-person.
        # No-op when author_label is None. (#963)
        verb = _rewrite_first_person(verb)
        obj = _rewrite_first_person(obj)
        legacy_context = _rewrite_first_person(legacy_context)
        # SVO synthesis fallback (#1113): when extract_all's combined
        # call (or a legacy-cached item) didn't return verb/object,
        # synthesize them deterministically from any predicate text we
        # have. Without this, claim.predicate_verb / object_phrase end
        # up NULL on every row from the combined call, blocking #1111
        # paragraph-composition with citation arrows.
        raw_verb_present = bool((item.get("verb") or "").strip())
        raw_obj_present = bool((item.get("object") or "").strip())
        verb, obj = _synthesize_svo_fallback(
            canonical or item.get("date") or item.get("fecha") or "",
            verb,
            obj,
            legacy_context,
        )
        # Section-typed default when nothing whatsoever was extractable:
        # keywords-style sections (bare strings — no description, no
        # context) leave verb/obj empty after the heuristic. Without a
        # default, claim.predicate_verb stays None and the #1113 invariant
        # is violated. Use the section label so the claim still composes
        # as a real (if minimal) sentence: "X is a concept." / "X is a
        # location." Honest about being a typed default rather than an
        # extraction.
        if not verb and not obj and entity_type is not None:
            verb = "is"
            type_label = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
            obj = f"a {type_label}"
        # Honest hybrid label: when our heuristic filled in the SVO,
        # tag the model so users can tell direct-LLM SVO from
        # synthesised SVO at audit time.
        svo_synthesised = (verb or obj) and not (raw_verb_present and raw_obj_present)
        claim_model_label = base_model_label
        if claim_model_label and svo_synthesised:
            claim_model_label = f"{claim_model_label}+heuristic-svo"

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
        source_bbox = item.get("source_bbox")
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

        # Per-claim confidence (#1113): explicit LLM-extracted SVO is
        # more reliable than synthesised; rejected claims get a floor
        # so they sort low without disappearing.
        if epistemic and getattr(epistemic, "value", "") == "rejected":
            claim_confidence = 0.3
        elif raw_verb_present and raw_obj_present:
            claim_confidence = 0.7
        else:
            claim_confidence = 0.5

        # Temporal scope (#904) — empty strings become None so the
        # KnowledgeClaim field stays NULL when the LLM doesn't date it.
        t_start = (item.get("time_start") or "").strip() or None
        t_end = (item.get("time_end") or "").strip() or None
        t_precision = (item.get("time_precision") or "").strip() or None
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
            normalized = str(normalized).strip()
            if normalized and not t_start and not t_end:
                if "/" in normalized:
                    start_raw, end_raw = normalized.split("/", 1)
                    t_start = start_raw.strip() or None
                    t_end = end_raw.strip() or None
                    t_precision = t_precision or "range"
                else:
                    t_start = normalized
                    t_end = normalized
                    if not t_precision:
                        if len(normalized) == 4:
                            t_precision = "year"
                        elif len(normalized) == 7:
                            t_precision = "month"
                        elif len(normalized) >= 10:
                            t_precision = "day"
            stem = normalized or date_text
            # Avoid double-period when predicate already ends in
            # terminal punctuation (#1113 polish).
            if predicate:
                _pred = predicate.rstrip()
                _suffix = "" if _pred.endswith((".", "!", "?")) else "."
                claim_text = f"{stem}: {_pred}{_suffix}"
            else:
                claim_text = stem
            meta["date_text"] = date_text
            meta["date_normalized"] = normalized
            meta["subject"] = stem
            # #1119 — reverse alias scan over the claim text + object +
            # excerpt. Date-style claims have no subject entity (the date
            # IS the subject), so any entity mention here is purely
            # secondary; the caller's entity_ids defaults to [].
            scan_text = " ".join(filter(None, [
                claim_text, predicate, excerpt or ""
            ]))
            mentioned = _scan_for_mentioned_entities(
                scan_text, alias_pairs, exclude=set()
            )
            claim_id = save_claim(
                db,
                text=claim_text,
                source_document_id=container_id,
                entity_ids=mentioned,
                source_excerpt=excerpt,
                source_page_label=page_label,
                source_char_start=char_start,
                source_char_end=char_end,
                claim_type=ctype or ClaimType.fact,
                metadata=meta,
                epistemic_status=epistemic,
                time_start=t_start,
                time_end=t_end,
                time_precision=t_precision,
                # SVO promotion (#984): also write to the typed
                # top-level fields. Date-style claims have an implicit
                # subject = the normalised date string.
                subject_canonical=stem,
                predicate_verb=verb or None,
                object_phrase=obj or None,
                # New SVO-style fields (#730): structured triples metadata
                svo_subject=stem,
                svo_verb=slug_verb(verb) if verb else None,
                svo_object=obj or None,
                # Provider attribution + confidence + language (#1113).
                provider=base_provider_label,
                model=claim_model_label,
                language=detected_language,
                confidence=claim_confidence,
                # #1123 Phase D — separate per-claim source_language
                # from the doc-level `language` arg (both point at
                # detected_language today; the distinction matters
                # when a doc has multilingual passages and a later
                # pass overrides per-claim) and record whether the
                # SVO came from the LLM or our heuristic fallback.
                source_language=detected_language,
                confidence_origin=(
                    "heuristic" if svo_synthesised else "llm"
                ),
                claim_recorded_at=doc_date,
            )
            if claim_id is not None:
                claims_written += 1
                written_claim_ids.append(claim_id)
                claim = db.get(KnowledgeClaim, claim_id)
                if claim is not None:
                    claims_to_embed.append(claim)
            continue

        # Entity-bearing section.
        if not canonical:
            # Sections with allow_null_subject (e.g. unattributed quotes) still
            # write a claim with subject=None so the inspector can surface them
            # rather than silently dropping them (#1099).
            if section.get("allow_null_subject") and (verb or obj or legacy_context):
                if verb or obj:
                    _pred = predicate.rstrip()
                    _suffix = "" if _pred.endswith((".", "!", "?")) else "."
                    claim_text = f"[unattributed] {_pred}{_suffix}".strip()
                else:
                    claim_text = legacy_context or "[unattributed]"
                mentioned = _scan_for_mentioned_entities(
                    " ".join(filter(None, [claim_text, excerpt or ""])),
                    alias_pairs,
                    exclude=set(),
                )
                claim_id = save_claim(
                    db,
                    text=claim_text,
                    source_document_id=container_id,
                    entity_ids=mentioned,
                    source_excerpt=excerpt,
                    source_page_label=page_label,
                    source_char_start=char_start,
                    source_char_end=char_end,
                    claim_type=ctype or ClaimType.fact,
                    metadata=meta,
                    epistemic_status=epistemic,
                    subject_canonical=None,
                    predicate_verb=verb or None,
                    object_phrase=obj or None,
                    # New SVO-style fields (#730): structured triples metadata
                    svo_subject=None,
                    svo_verb=slug_verb(verb) if verb else None,
                    svo_object=obj or None,
                    provider=base_provider_label,
                    model=claim_model_label,
                    language=detected_language,
                    confidence=claim_confidence,
                    source_language=detected_language,
                    confidence_origin=("heuristic" if svo_synthesised else "llm"),
                    claim_recorded_at=doc_date,
                )
                if claim_id is not None:
                    claims_written += 1
                    written_claim_ids.append(claim_id)
                    claim = db.get(KnowledgeClaim, claim_id)
                    if claim is not None:
                        claims_to_embed.append(claim)
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
            # Avoid double-period when the LLM-emitted object already
            # ends in terminal punctuation (#1113 polish).
            _pred = predicate.rstrip()
            _suffix = "" if _pred.endswith((".", "!", "?")) else "."
            claim_text = f"{canonical} {_pred}{_suffix}".strip()
        elif legacy_context:
            claim_text = f"{canonical}: {legacy_context}"
        else:
            claim_text = canonical
        entity_description = _sanitize_entity_description(
            predicate or None, canonical
        )
        if (desc_violation := entity_description_violation(
            predicate or None, canonical
        )):
            invariant_violations.append(desc_violation)
        entity_id = upsert_entity(
            db,
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=aliases if isinstance(aliases, list) else [],
            # The entity's curated description used to be the raw
            # context; with SVO it's the full predicate so users still
            # see a useful blurb in the inspector. Sanitised first to
            # reject degenerate fragments ("called", "noted") that
            # leak when the LLM can't compose a real predicate. (#1016)
            description=entity_description,
            # container_id here is the per-page target_doc_id (#1562) —
            # scope the entity to the page it was extracted from.
            source_document_id=container_id,
        )
        if entity_id is None:
            continue
        written_entity_ids.append(entity_id)
        # #1119 — reverse alias scan over claim text + predicate + excerpt.
        # Subject entity is already in entity_ids; the scan extends with
        # any OTHER known entities mentioned. Example: "Chocó is part of
        # the Andes region" — subject is Chocó, scan picks up "Andes
        # region" too if it's a known entity.
        scan_text = " ".join(filter(None, [
            claim_text, predicate, excerpt or ""
        ]))
        mentioned = _scan_for_mentioned_entities(
            scan_text, alias_pairs, exclude={entity_id}
        )
        claim_id = save_claim(
            db,
            text=claim_text,
            source_document_id=container_id,
            entity_ids=[entity_id, *mentioned],
            source_excerpt=excerpt,
            source_page_label=page_label,
            source_char_start=char_start,
            source_char_end=char_end,
            source_bbox=source_bbox,
            claim_type=ctype or ClaimType.fact,
            metadata=meta,
            epistemic_status=epistemic,
            claim_location=(
                canonical
                if entity_type == EntityType.location and canonical
                else None
            ),
            # SVO promotion (#984): typed top-level fields. The
            # subject IS the entity, so subject_entity_id resolves
            # the lookup at write time.
            subject_canonical=canonical,
            subject_entity_id=entity_id,
            predicate_verb=verb or None,
            object_phrase=obj or None,
            # New SVO-style fields (#730): structured triples metadata
            svo_subject=canonical,
            svo_verb=slug_verb(verb) if verb else None,
            svo_object=obj or None,
            # Provider attribution + confidence + language (#1113).
            provider=base_provider_label,
            model=claim_model_label,
            language=detected_language,
            confidence=claim_confidence,
            # #1123 Phase D — see the parallel date-style block above
            # for rationale on source_language + confidence_origin.
            source_language=detected_language,
            confidence_origin=(
                "heuristic" if svo_synthesised else "llm"
            ),
            claim_recorded_at=doc_date,
        )
        entities_written += 1
        if claim_id is not None:
            claims_written += 1
            written_claim_ids.append(claim_id)
            claim = db.get(KnowledgeClaim, claim_id)
            if claim is not None:
                claims_to_embed.append(claim)

    if claims_to_embed:
        db.schedule_claim_embeddings(claims_to_embed)

    # #1003: structured per-page summary. If items_in > 0 but
    # entities_written + claims_written == 0, a page's items were all
    # dropped (no canonical name, all deduped, etc.) — that's the
    # silent-failure signature the issue describes.
    logger.info(
        f"_write_kg_rows: {section.get('name')} "
        f"{page_label or 'whole-doc'} on {container_id} — "
        f"items_in={items_in} entities_written={entities_written} "
        f"claims_written={claims_written}"
    )
    # #1017 layer 2: when items were lost or degraded on the way in,
    # name the reasons at WARNING so the activity log shows WHY a page
    # is thin instead of leaving it as an unexplained items_in gap.
    if invariant_violations:
        logger.warning(
            f"_write_kg_rows: {section.get('name')} "
            f"{page_label or 'whole-doc'} on {container_id} — "
            f"invariant violations: {summarize_violations(invariant_violations)}"
        )
    return written_entity_ids, written_claim_ids


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
        config_schema=merge_config_schema(
            BASE_CONFIG_SCHEMA,
            _LANGUAGE_CONFIG,
            _NER_CONFIG,
        ),
        # Expose the prompt for transparency. The JSON-schema portion is a
        # parser contract — editing the prompt is allowed but breaking the
        # schema_key or shape will cause silent parse failures.
        default_prompt=_build_section_prompt(section, "Spanish"),
        sort_order=10 + _SECTIONS.index(section),
    )(_tool)

    return _tool


# Exported so __init__.py importing this module triggers registration.
EXTRACTORS = {section["name"]: _make_registered(section) for section in _SECTIONS}
