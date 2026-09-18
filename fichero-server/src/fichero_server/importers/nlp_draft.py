"""Free NLP draft layer at import (#4823).

Ruling (nlp-layer-rulings, 2026-09-04): the free NLP layer (spaCy parse,
NER) runs automatically on every text-bearing page at import, like
embeddings. Its output is a DRAFT that later LLM/VLM workflow passes
refine, and the user curates: "cheap NLP proposes -> LLM/VLM normalizes ->
user curates." This module is only the first arrow.

Reuses, deliberately, rather than rebuilding:
- ``knowledge/spacy_ner.py::extract_entities`` and
  ``knowledge/spacy_svo.py::propose_triples``/``filter_proposals`` — the
  SAME free, deterministic, no-LLM proposers already shipped and tested
  elsewhere (spacy_svo today is consumed only as a validator of LLM output;
  this is its first use as a direct, if noisier, proposer).
- ``workflows/tools/extractors.py::_write_kg_rows`` — the ONE existing
  entity/claim writer every extraction tool (LLM or free) writes through.
  Reusing it, rather than a parallel writer, is what makes the draft-layer
  and curation-persistence guarantees below come for free instead of being
  reimplemented:
    * every new row lands ``curation_state=unreviewed`` (the field's own
      default) -- this IS the "draft" marker the ruling asks for, no new
      field or migration needed.
    * ``upsert_entity``/``save_claim`` match on identity before writing, so
      a draft never duplicates or downgrades a row a human or an LLM pass
      already produced -- a later LLM/VLM run on the same page either
      matches the same row (records additional attribution) or, if the
      draft was corrected, hits ``curation_guard``'s conflict tracking
      instead of silently overwriting the correction.
- ``workflows/tools/_workflow_change_emit.py::emit_workflow_kg_changes_for_db``
  — the SAME coalesced ``entity.updated``/``claim.updated``/``document.updated``
  change-stream announcement the LLM extraction tools already use, called
  once per document, never once per row.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.db import Database
    from fichero_server.models import Document

logger = logging.getLogger(__name__)

#: App-wide setting (Settings > General > Ingestion, beside auto-extract/
#: auto-embed). The RATIFIED default is ON ("no toggle" reads as "always
#: runs unless you turn it off", the same reading `auto_embed` already
#: gets -- not "no way to turn it off at all"). Swift-side settings row is
#: a separate (Swift-lane) piece; this key is what it would read/write.
AUTO_NLP_SETTING_KEY = "ingestion.auto_nlp"

# TEMPORARY MANAGER DECISION, reversible in one line: default is OFF for
# now, even though the ruling's default is ON. Reason: this writes into
# real research libraries on every import with no Settings row yet to turn
# it off and no way to take the rows back (S3's purge action closes that
# second gap). Flip `_DEFAULT_ENABLED` back to True once (a) a Settings row
# exists and (b) draft output has been reviewed against real OCR'd/
# handwritten material, not just clean stub text.
_DEFAULT_ENABLED = False

# Local copy of the small true/false vocabulary already duplicated this way
# in security/multiuser.py, security/discovery.py, security/remote_backend.py
# -- one tiny constant per settings module is this codebase's own precedent,
# not worth centralizing for a fourth caller.
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def auto_nlp_enabled() -> bool:
    """Whether the free NLP draft stage should run at import.

    See `_DEFAULT_ENABLED`'s comment for why the default is temporarily OFF
    rather than the ruling's ON. An explicit value always wins either way --
    this is a default, not a lockout.
    """
    from fichero_server.db.app import get_app_db

    try:
        value = get_app_db().get_setting(AUTO_NLP_SETTING_KEY)
    except Exception as exc:  # pragma: no cover - defensive, matches the
        # multiuser.py precedent: a setting read failure never blocks import.
        logger.warning("Could not read %s setting: %s", AUTO_NLP_SETTING_KEY, exc)
        return _DEFAULT_ENABLED
    if value is None:
        return _DEFAULT_ENABLED
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return _DEFAULT_ENABLED  # unrecognised value -> the default, not a guess


def needs_nlp(doc: "Document") -> bool:
    """Same population as embedding (#4823 ruling: "like embeddings") --
    any page that actually has extracted text."""
    return bool(doc.page_content)


# =============================================================================
# S2: the draft-quality gate (team-lead review, 2026-09-18).
#
# `spacy_ner.extract_entities` has no garbage gate of its own -- on the
# workflow path that's fine, because an LLM cleanup pass always runs after
# it. This draft layer has NO such pass. On OCR'd historical text (small
# spaCy models over handwritten/colonial-Spanish material) that gap turns
# into thousands of junk draft rows in a real library.
#
# `api/routes/entity/entities.py::_is_garbage_entity_name` is the existing
# engine-side floor (its own docstring already says "same heuristic as
# Swift isOcrGarbage") but it is WEAKER than the Swift original -- it only
# rejects a name with literally zero letters, missing the Swift version's
# letter-RATIO check (`fichero/fichero/Models/EntityNameHeuristics.swift`:
# < 2 chars, all-non-letter, OR fewer than half the characters are letters).
# `_is_ocr_garbage` below is a straight port of the Swift rule, so the two
# platforms agree on what counts as noise; it is intentionally NOT wired
# into `_is_garbage_entity_name` (a different, already-tested, general-
# purpose consumer) -- only into this draft-specific gate, which then adds
# floors the entity-creation route has no reason to need.
# =============================================================================

_DRAFT_MIN_LENGTH = 3
_DRAFT_MIN_LETTERS = 2
_DRAFT_MIN_LETTER_RATIO = 0.5
_DRAFT_MAX_ENTITIES_PER_DOCUMENT = 200

# Concepts are where small spaCy models hallucinate most on this corpus:
# ES `MISC` and EN `WORK_OF_ART`/`LAW` all map to Fichero's "concept" type
# in `spacy_ner._SPACY_TO_FICHERO_*` -- dropped from the draft layer
# entirely in v1, not just gated on name quality.
_DRAFT_EXCLUDED_TYPES = frozenset({"concept"})

# Single common function/stop words that occasionally survive span
# extraction as a bare "name" (a stray "el", "de", "the") -- not an entity,
# noise wearing capitalisation loss. Deliberately short: a real short name
# that happens to be a common word in another sense ("Fe", a Spanish given
# name) is a risk we accept rather than build a much larger stopword list
# for a v1 gate.
_DRAFT_COMMON_WORDS = frozenset({
    "el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "que",
    "the", "and", "of", "in", "a", "an", "to", "for", "is", "are",
})


def _is_ocr_garbage(name: str) -> bool:
    """Port of Swift's ``EntityNameHeuristics.isOcrGarbage`` (#1168), kept
    in sync so a name that reads as garbage on one platform reads as
    garbage on the other: fewer than 2 characters, no letters at all, or
    under half the characters are letters."""
    stripped = name.strip()
    if len(stripped) < 2:
        return True
    letters = sum(1 for c in stripped if c.isalpha())
    if letters == 0:
        return True
    return (letters / len(stripped)) < _DRAFT_MIN_LETTER_RATIO


def passes_draft_quality_gate(name: str, fichero_type: str) -> bool:
    """The v1 free-draft floor (S2) -- stricter than `_is_ocr_garbage`
    alone, because nothing downstream of this layer cleans up its mistakes
    the way an LLM pass cleans up the workflow tools' spaCy pre-pass."""
    if fichero_type in _DRAFT_EXCLUDED_TYPES:
        return False
    stripped = name.strip()
    if len(stripped) < _DRAFT_MIN_LENGTH:
        return False
    letters = sum(1 for c in stripped if c.isalpha())
    if letters < _DRAFT_MIN_LETTERS:
        return False
    if _is_ocr_garbage(stripped):
        return False
    if stripped.lower() in _DRAFT_COMMON_WORDS:
        return False
    return True


@dataclass
class NlpDraftResult:
    entity_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    #: None = ran (even if it proposed nothing -- an empty page is a
    #: legitimate, non-error outcome). Set = a SPECIFIC, visible reason,
    #: never a silent empty stand-in for a real failure.
    error: str | None = None
    #: True when the per-document entity cap (`_DRAFT_MAX_ENTITIES_PER_
    #: DOCUMENT`) dropped surviving entities -- visible on the document,
    #: never a silent truncation.
    truncated: bool = False


def run_nlp_draft(
    db: "Database",
    doc: "Document",
    *,
    language: str | None = None,
    ner_fn=None,
    svo_fn=None,
    filter_fn=None,
) -> NlpDraftResult:
    """Run the free NER+SVO pass over one document's text and write it.

    Never raises -- a bad page loses its NLP draft, not the import (same
    contract as ``_thumbnail_stage``/``_embed_stage`` in
    ``importers/derivatives.py``). ``ner_fn``/``svo_fn``/``filter_fn`` are
    injection seams for tests (a stubbed extractor runs everywhere; the real
    spaCy pipeline only where the model is actually installed).
    """
    from fichero_server.knowledge import spacy_ner, spacy_svo

    ner_fn = ner_fn or spacy_ner.extract_entities
    svo_fn = svo_fn or spacy_svo.propose_triples
    filter_fn = filter_fn or spacy_svo.filter_proposals

    text = doc.page_content or ""
    if not text.strip():
        return NlpDraftResult()

    # Statement-language-matches-the-document ruling: resolve the document's
    # own language (`language` param, when given, is the top-precedence
    # `requested` override `resolve_language` already defines; absent that,
    # the document's own recorded/detected language wins -- never a global
    # default overriding it), fall back to the lightweight heuristic only
    # when nothing else answers.
    from fichero_server.llm.language_policy import resolve_language

    resolution = resolve_language(requested=language, document=doc, text=text)
    lang = (
        spacy_ner.normalize_language(resolution.language)
        if resolution.is_known
        else None
    ) or spacy_ner.detect_language(text)

    if not spacy_ner.is_pipeline_available(lang):
        return NlpDraftResult(
            error=f"NLP model not installed for language={lang!r}"
        )

    try:
        entities = ner_fn(text, language=lang)
        proposals = svo_fn(text, language=lang)
        kept, _rejected = filter_fn(proposals, text)
    except Exception as exc:  # a parser bug must not fail the import
        logger.warning("nlp_draft: extraction failed for doc %s: %s", doc.id, exc)
        return NlpDraftResult(error=f"{type(exc).__name__}: {exc}")

    # S2 (team-lead review): the draft-specific quality gate + a visible
    # per-document cap. Applied BEFORE anything is written, not after --
    # a dropped span never reaches `_write_kg_rows` at all.
    gated_entities = [
        span for span in entities
        if passes_draft_quality_gate(span.text, span.fichero_type)
    ]
    truncated = len(gated_entities) > _DRAFT_MAX_ENTITIES_PER_DOCUMENT
    if truncated:
        logger.info(
            "nlp_draft: capped draft entities for doc %s at %d (had %d)",
            doc.id, _DRAFT_MAX_ENTITIES_PER_DOCUMENT, len(gated_entities),
        )
        gated_entities = gated_entities[:_DRAFT_MAX_ENTITIES_PER_DOCUMENT]

    entity_ids, claim_ids = _write_draft(db, doc, gated_entities, kept, text)

    if entity_ids or claim_ids:
        from fichero_server.workflows.tools._workflow_change_emit import (
            emit_workflow_kg_changes_for_db,
        )

        # Once per document, coalesced -- never per row, never per page in a
        # bulk import (same discipline the embed stage's own docstring
        # explains for why IT emits nothing at all).
        emit_workflow_kg_changes_for_db(
            db, entity_ids=entity_ids, claim_ids=claim_ids, document_ids=[doc.id],
        )

    return NlpDraftResult(entity_ids=entity_ids, claim_ids=claim_ids, truncated=truncated)


def _write_draft(db, doc, entities, kept_proposals, text: str) -> tuple[list[str], list[str]]:
    """Shape spaCy's typed entities + filtered SVO proposals into
    `_write_kg_rows` calls, one per detected Fichero entity_type (the writer
    upserts against exactly one type per call).

    ``entities`` has already passed the S2 draft-quality gate by the time it
    reaches here -- a dropped span's TEXT also never enters
    ``type_by_subject`` below, so an SVO proposal whose subject was gated
    out is dropped too, the same "untyped subject" path a genuinely
    undetected subject takes.

    An SVO proposal's subject only becomes a claim when it resolves to a
    Fichero type the NER pass actually detected on this same page -- an
    untyped subject is dropped, not guessed, because `_write_kg_rows`
    requires a section `entity_type` to upsert against (prefer-raise's
    cousin: prefer absence over a wrong type).
    """
    from fichero_server.models.knowledge import EntityType
    from fichero_server.workflows.tools.extractors import _write_kg_rows

    entity_ids: list[str] = []
    claim_ids: list[str] = []

    page_label = (doc.metadata or {}).get("page_label") if doc.metadata else None

    entities_by_type: dict[str, list[dict]] = {}
    type_by_subject: dict[str, str] = {}
    for span in entities:
        entities_by_type.setdefault(span.fichero_type, []).append(
            {"name": span.text, "source_text": span.text}
        )
        type_by_subject[span.text] = span.fichero_type

    for fichero_type, items in entities_by_type.items():
        try:
            section_type = EntityType(fichero_type)
        except ValueError:  # pragma: no cover - defensive
            continue
        created, claims = _write_kg_rows(
            db,
            {"name": "nlp_draft_entities", "entity_type": section_type},
            items,
            doc.id,
            page_label=page_label,
            provider="spacy",
            model="spacy_ner",
        )
        entity_ids.extend(created)
        claim_ids.extend(claims)

    svo_by_type: dict[str, list[dict]] = {}
    for proposal in kept_proposals:
        subject_type = type_by_subject.get(proposal.subject)
        if subject_type is None:
            continue
        svo_by_type.setdefault(subject_type, []).append(proposal.as_item())

    for fichero_type, items in svo_by_type.items():
        try:
            section_type = EntityType(fichero_type)
        except ValueError:  # pragma: no cover - defensive
            continue
        created, claims = _write_kg_rows(
            db,
            {"name": "nlp_draft_svo", "entity_type": section_type},
            items,
            doc.id,
            page_label=page_label,
            source_excerpt=text[:500],
            provider="spacy",
            model="spacy_svo",
        )
        entity_ids.extend(created)
        claim_ids.extend(claims)

    return entity_ids, claim_ids


__all__ = [
    "AUTO_NLP_SETTING_KEY",
    "auto_nlp_enabled",
    "needs_nlp",
    "NlpDraftResult",
    "run_nlp_draft",
]
