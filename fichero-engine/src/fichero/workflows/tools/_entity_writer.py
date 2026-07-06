"""Entity writer helpers for catalogue extractors.

Centralizes the upsert + claim save pattern so each extractor in
`extractors.py` doesn't reimplement it. Bridges structured-extraction
outputs (people, places, organizations, events, concepts) into the
existing knowledge-graph layer (`KnowledgeEntity`, `KnowledgeClaim`).

See `docs/architecture/typed_entity_storage.md` §0 for the design and
`docs/superpowers/plans/2026-04-28-typed-entity-storage.md` for the
implementation plan (#728).
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from functools import wraps
from typing import Optional

from fichero.db import Database
from fichero.kg._common import is_bare_is_a_copula
from fichero.knowledge_models import (
    AttributionRole,
    AttributionStep,
    ClaimCurationState,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    ClaimType,
    ClaimRelationType,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    EvidenceBasis,
    EpistemicStatus,
    EvidentialDateRange,
    EvidentialPlace,
    GeoPoint,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    PlaceGeometryType,
    QuotationKind,
    SourceSupport,
)

logger = logging.getLogger(__name__)

_ENTITY_UPSERT_LOCK = threading.RLock()


def _serialized_entity_upsert(func):
    """Run KnowledgeEntity dedup/update work through one process-local lane."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _ENTITY_UPSERT_LOCK:
            return func(*args, **kwargs)

    return wrapper


def _norm_rule_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def _matching_entity_resolution_rules(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
) -> list[EntityResolutionRule]:
    normalized_name = _norm_rule_text(canonical_name)
    rules = [
        rule
        for rule in db.query(EntityResolutionRule)
        if _norm_rule_text(rule.match_canonical_name) == normalized_name
    ]
    matched = [
        rule
        for rule in rules
        if rule.match_entity_type is None or rule.match_entity_type == entity_type
    ]
    matched.sort(key=lambda rule: (rule.created_at, rule.id))
    return matched


def _apply_entity_resolution_rules(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
) -> tuple[str, EntityType] | None:
    current_name = canonical_name
    current_type = entity_type
    seen: set[tuple[str, str]] = set()

    for _ in range(8):
        loop_key = (_norm_rule_text(current_name), current_type.value)
        if loop_key in seen:
            logger.warning(
                "upsert_entity: not writing %r/%s after resolution-rule loop detected; suppressing due to suspected cycle/overflow",
                current_name,
                current_type.value,
            )
            return None
        seen.add(loop_key)

        rules = _matching_entity_resolution_rules(db, current_name, current_type)
        if not rules:
            return current_name, current_type

        suppress_rule = next(
            (rule for rule in rules if rule.rule_type == EntityResolutionRuleType.suppress),
            None,
        )
        if suppress_rule is not None:
            logger.info(
                "upsert_entity: suppressing %r/%s via rule %s",
                current_name,
                current_type.value,
                suppress_rule.id,
            )
            return None

        reclassify_rule = next(
            (
                rule
                for rule in rules
                if rule.rule_type == EntityResolutionRuleType.reclassify
                and rule.target_entity_type is not None
                and rule.target_entity_type != current_type
            ),
            None,
        )
        if reclassify_rule is not None:
            logger.info(
                "upsert_entity: reclassifying %r %s -> %s via rule %s",
                current_name,
                current_type.value,
                reclassify_rule.target_entity_type.value,
                reclassify_rule.id,
            )
            current_type = reclassify_rule.target_entity_type
            continue

        redirect_rule = next(
            (
                rule
                for rule in rules
                if rule.rule_type in {
                    EntityResolutionRuleType.merge_into,
                    EntityResolutionRuleType.alias,
                }
                and rule.target_canonical_name
            ),
            None,
        )
        if redirect_rule is not None:
            redirected_name = redirect_rule.target_canonical_name.strip()
            redirected_type = redirect_rule.target_entity_type or current_type
            logger.info(
                "upsert_entity: redirecting %r/%s -> %r/%s via rule %s",
                current_name,
                current_type.value,
                redirected_name,
                redirected_type.value,
                redirect_rule.id,
            )
            current_name = redirected_name
            current_type = redirected_type
            continue

        return current_name, current_type

    logger.warning(
        "upsert_entity: not writing %r/%s after resolution-rule iteration cap reached; suppressing due to suspected cycle/overflow",
        current_name,
        current_type.value,
    )
    return None

def _matching_claim_suppression_rules(
    db: Database,
    subject_canonical: str | None,
    predicate_verb: str | None,
    object_phrase: str | None,
) -> list[ClaimSuppressionRule]:
    subject_norm = _norm_rule_text(subject_canonical)
    predicate_norm = _norm_rule_text(predicate_verb)
    object_norm = _norm_rule_text(object_phrase)
    matches: list[ClaimSuppressionRule] = []
    for rule in db.all(ClaimSuppressionRule):
        if rule.match_subject_name and _norm_rule_text(rule.match_subject_name) != subject_norm:
            continue
        if rule.match_predicate_verb and _norm_rule_text(rule.match_predicate_verb) != predicate_norm:
            continue
        if rule.match_object_phrase and _norm_rule_text(rule.match_object_phrase) != object_norm:
            continue
        if rule.suppress_is_a_copulas and not is_bare_is_a_copula(predicate_verb, object_phrase):
            continue
        matches.append(rule)
    matches.sort(key=lambda rule: (rule.created_at, rule.id))
    return matches


def _effective_claim_suppression_action(
    rule: ClaimSuppressionRule,
    predicate_verb: str | None,
    object_phrase: str | None,
) -> ClaimSuppressionRuleAction:
    if rule.suppress_is_a_copulas and is_bare_is_a_copula(predicate_verb, object_phrase):
        return ClaimSuppressionRuleAction.demote
    return rule.action


def _claim_suppression_action(
    db: Database,
    subject_canonical: str | None,
    predicate_verb: str | None,
    object_phrase: str | None,
) -> ClaimSuppressionRuleAction | None:
    matched = _matching_claim_suppression_rules(
        db,
        subject_canonical=subject_canonical,
        predicate_verb=predicate_verb,
        object_phrase=object_phrase,
    )
    if not matched:
        return None

    actions = [
        _effective_claim_suppression_action(rule, predicate_verb, object_phrase)
        for rule in matched
    ]
    if ClaimSuppressionRuleAction.prune in actions:
        return ClaimSuppressionRuleAction.prune
    if ClaimSuppressionRuleAction.disable in actions:
        return ClaimSuppressionRuleAction.disable
    return ClaimSuppressionRuleAction.demote


# Admin-subdivision qualifier vocabulary (#1114 issue 2)
# ------------------------------------------------------
# Words that act as "type qualifiers" on a place name — adding or
# stripping them doesn't change which entity is referred to. "Chocó"
# vs "Chocó department" is the same entity; "Chocó" vs "Chocó River"
# is NOT (the river and the department are different things).
#
# Limited deliberately to political / administrative subdivisions so
# we don't accidentally collapse genuinely-distinct entities. Adding
# "river" / "mountain" / "sea" here would break that contract.
#
# Spanish equivalents because the corpus is heavily Hispano-American.
# Add other languages as the corpus extends.
_ADMIN_SUFFIXES = frozenset({
    # English
    "department", "province", "state", "region", "county", "district",
    "territory", "republic",
    # Spanish
    "departamento", "provincia", "región", "regional", "condado",
    "distrito", "territorio", "república",
})

_ADMIN_PREFIXES = frozenset({
    "the", "el", "la", "los", "las", "le", "les",
})


def _fold_accents(s: str) -> str:
    """Strip diacritics so "Peña" folds onto "Pena" (#1811).

    NFKD-decompose then drop the combining marks. Case is left to the
    caller (token helpers lowercase separately). Folding is deliberately
    accent-only — it does NOT transliterate (ñ→n is a side effect of
    decomposition, but ß/ø/đ that have no canonical decomposition are
    left intact rather than guessed at), keeping the transform lossless
    enough that distinct names ("Müller" vs "Mahler") don't collide.
    """
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokenise_lower(s: str) -> list[str]:
    """Split a name into lowercase alphanumeric tokens."""
    cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())
    return [tok for tok in cleaned.split() if tok]


def _normalized_match_key(name: str) -> str:
    """Conservative high-precision identity key for a name (#1811).

    Accent-fold, lowercase, strip punctuation/whitespace, drop leading
    articles and trailing admin-subdivision qualifiers, then re-join.
    Two names with the same key are the *same* entity for matching
    purposes — this captures accent variants ("Peña"/"Pena"), trailing
    punctuation ("San Pablo."), case, and article/qualifier noise
    ("the X"/"X department") without any fuzzy tolerance, so it never
    collapses genuinely distinct names ("San Pablo" vs "San Juan").
    """
    return " ".join(_strip_admin_qualifiers(_tokenise_lower(_fold_accents(name))))


def _normalized_claim_svo_key(
    subject: str | None,
    predicate: str | None,
    object_phrase: str | None,
) -> tuple[str, str, str] | None:
    """High-precision identity key for structured SVO claims (#1805).

    Mirrors the entity normalized key for each SVO component: accent-fold,
    case-fold, punctuation/whitespace folding, and article/admin-qualifier
    stripping. It deliberately does not translate or synonym-match; two
    claims collapse only when all three normalized components are identical.
    """
    parts = (
        _normalized_match_key(subject or ""),
        _normalized_match_key(predicate or ""),
        _normalized_match_key(object_phrase or ""),
    )
    return parts if all(parts) else None


def _strip_admin_qualifiers(tokens: list[str]) -> list[str]:
    """Drop leading articles ('the', 'el', 'la') and trailing
    administrative-subdivision words ('department', 'province').
    Returns the core entity tokens.
    """
    while tokens and tokens[0] in _ADMIN_PREFIXES:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _ADMIN_SUFFIXES:
        tokens = tokens[:-1]
    return tokens


# Embedding auto-merge precision gate (#1907)
# -------------------------------------------
# A high e5-large cosine alone over-merges surface-distinct but
# semantically-similar names ("San Pablo" vs "San Juan" — both
# saint-name places land at ~0.93 cosine). Before honouring an
# embedding auto-merge we ALSO require a lexical agreement signal so
# the two surface forms actually look like the same name.
_AUTO_MERGE_LEXICAL_SEQ_FLOOR = 0.80
_AUTO_MERGE_MIN_SHARED_TOKENS = 2


def _significant_tokens(s: str) -> set[str]:
    """Accent-folded, lowercased tokens of length > 2 (drops generic
    short connectors like 'of'/'on'/'la' and single letters).
    """
    return {tok for tok in _tokenise_lower(_fold_accents(s)) if len(tok) > 2}


def _lexical_agreement(name_a: str, name_b: str) -> bool:
    """Precision gate for embedding auto-merge (#1907).

    Returns True only when the two surface forms agree lexically — via
    EITHER signal:

    - **High SequenceMatcher ratio** on accent-folded forms — catches
      accent / spacing variants of the *same* name ("Bogotá"/"Bogota"
      → 1.0, "San Pablo"/"San Pabloo" → ~0.94).
    - **>= 2 shared significant tokens** — catches verbose paraphrases
      that share content words ("Narrator's Account of Racial Economic
      Exclusion" / "Narrator's Monologue on Race and Economic
      Marginalization" share {narrator, economic}).

    Surface-distinct names that merely share a single generic token
    ("San Pablo" vs "San Juan" — only "san" in common, seq ratio
    ~0.59) fail BOTH signals and are therefore NOT auto-merged on
    embedding cosine alone; they route to the human review queue.
    """
    from difflib import SequenceMatcher

    folded_a = _fold_accents(name_a.lower())
    folded_b = _fold_accents(name_b.lower())
    if SequenceMatcher(None, folded_a, folded_b).ratio() >= _AUTO_MERGE_LEXICAL_SEQ_FLOOR:
        return True
    shared = _significant_tokens(name_a) & _significant_tokens(name_b)
    return len(shared) >= _AUTO_MERGE_MIN_SHARED_TOKENS


def _admin_qualifier_match(a: str, b: str) -> bool:
    """Return True when ``a`` and ``b`` reduce to the same non-empty
    core tokens after dropping leading articles and trailing
    admin-qualifier suffixes.

    Examples — match:
        "Chocó" ↔ "Chocó department"
        "the Cabildo" ↔ "Cabildo"
        "Province of Antioquia" ↔ "Antioquia"   (after future stem rule)
        "el Atrato" ↔ "Atrato"

    Examples — no match:
        "Chocó" ↔ "Chocó River"          (River isn't in the vocab)
        "Cauca" ↔ "Cauca Valley"         (Valley isn't admin)
        "Bogotá" ↔ "Bogotá District"     (District IS in vocab, OK)
        "Lima" ↔ "Lima"                   (different types still need
                                           upsert's type-conflict check;
                                           this is name-only)
    """
    # Accent-fold (#1811) so "Peña" / "Pena department" reduce to the
    # same core tokens. Folding happens here rather than in
    # `_tokenise_lower` so the tokeniser's surface-preserving contract
    # (used elsewhere) is unchanged.
    core_a = _strip_admin_qualifiers(_tokenise_lower(_fold_accents(a)))
    core_b = _strip_admin_qualifiers(_tokenise_lower(_fold_accents(b)))
    return bool(core_a) and core_a == core_b


def _source_authority_weight(db: Database, doc_id: str) -> float:
    """Return the source-authority weight for one source document."""
    from fichero.models import AUTHORITY_WEIGHTS, Document

    doc = db.get(Document, doc_id)
    if doc is None:
        _warn_missing_source_document(doc_id, context="source authority")
        return 1.0
    authority = getattr(doc.source_authority, "value", doc.source_authority)
    if not isinstance(authority, str):
        authority = "unknown"
    return AUTHORITY_WEIGHTS.get(authority, 1.0)


def _warn_missing_source_document(doc_id: str, *, context: str) -> None:
    logger.warning(
        "Missing source document %s while deriving %s; using no substitute document.",
        doc_id,
        context,
    )


def _weighted_corroboration_count(db: Database, source_ids: set[str]) -> float:
    """Sum authority weights for a claim's distinct source documents."""
    return sum(_source_authority_weight(db, doc_id) for doc_id in source_ids)


def _fuzzy_match_existing(
    existing: list[KnowledgeEntity],
    canonical_name: str,
    threshold: float = 0.78,
) -> Optional[KnowledgeEntity]:
    """Return the best fuzzy match for ``canonical_name`` among existing
    entities of the same type, or None if nothing scores above threshold.

    Handles two divergence patterns observed on per-page extraction (#897):
    - **Surface variation**: "Eugenio Córdoba" vs "Eugenio Cordoba" vs
      "E. Córdoba". Caught by SequenceMatcher token-set similarity.
    - **Rephrasing the same recurring scene as N events**: the LLM
      titles the same monologue differently per page ("Narrator's
      Account of Racial Economic Exclusion" / "Narrator's Monologue
      on Race and Economic Marginalization" / etc.). Caught by
      token-overlap on the noun phrase after stop-word removal.

    Threshold defaults to 0.78 — empirically separates the 6-event
    monologue cluster (~0.85 between any two) from genuinely distinct
    events ("Filing of the Petition" vs "Sale of the Estate" — 0.30).

    The match is a heuristic, not a knowledge-graph linker. For a real
    entity-resolution pipeline we'd swap in splink or dedupe.io with
    learned model weights (#897 follow-up).
    """
    from difflib import SequenceMatcher

    if not canonical_name or not existing:
        return None

    # Normalise: accent-fold (#1811), lower, drop punctuation. Token-set
    # similarity is more forgiving of reordering than raw
    # SequenceMatcher.ratio. Diacritic folding makes "Peña"/"Pena" and
    # "Bogotá"/"Bogota" score as identical instead of 0.75 (which fell
    # under the 0.78 threshold and silently created near-duplicates).
    def _tokens(s: str) -> set[str]:
        folded = _fold_accents(s.lower())
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in folded)
        return {tok for tok in cleaned.split() if len(tok) > 2}

    def _single_token_suffix_noise_match(a: str, b: str) -> bool:
        tokens_a = _tokenise_lower(_fold_accents(a))
        tokens_b = _tokenise_lower(_fold_accents(b))
        if len(tokens_a) != 1 or len(tokens_b) != 1:
            return False
        left, right = tokens_a[0], tokens_b[0]
        shorter, longer = sorted((left, right), key=len)
        if len(shorter) < 5 or not longer.startswith(shorter):
            return False
        suffix = longer[len(shorter):]
        return 0 < len(suffix) <= 3 and longer.endswith(shorter[-1])

    # High-precision short-circuit: identical normalized identity key
    # (accent/case/punctuation/article/admin-qualifier folded) is a
    # guaranteed-safe merge — no fuzzy tolerance, so distinct names
    # can never collide here.
    needle_key = _normalized_match_key(canonical_name)
    if needle_key:
        for ent in existing:
            if _normalized_match_key(ent.canonical_name) == needle_key:
                return ent
            if _single_token_suffix_noise_match(
                canonical_name, ent.canonical_name
            ):
                return ent

    needle_tokens = _tokens(canonical_name)
    needle_lower = _fold_accents(canonical_name.lower())

    best: tuple[float, Optional[KnowledgeEntity]] = (0.0, None)
    for ent in existing:
        # Two metrics, take the max so either signal can hit threshold.
        seq_ratio = SequenceMatcher(
            None, needle_lower, _fold_accents(ent.canonical_name.lower())
        ).ratio()
        ent_tokens = _tokens(ent.canonical_name)
        if needle_tokens and ent_tokens:
            intersection = len(needle_tokens & ent_tokens)
            union = len(needle_tokens | ent_tokens)
            token_ratio = intersection / union if union else 0.0
        else:
            token_ratio = 0.0
        score = max(seq_ratio, token_ratio)
        if score > best[0]:
            best = (score, ent)

    return best[1] if best[0] >= threshold else None


def _coerce_date_values(
    values: Optional[list[EvidentialDateRange | dict]],
) -> list[EvidentialDateRange]:
    return [
        value
        if isinstance(value, EvidentialDateRange)
        else EvidentialDateRange.model_validate(value)
        for value in values or []
    ]


def _coerce_place_values(
    values: Optional[list[EvidentialPlace | dict]],
) -> list[EvidentialPlace]:
    return [
        value
        if isinstance(value, EvidentialPlace)
        else EvidentialPlace.model_validate(value)
        for value in values or []
    ]


def _coerce_attribution_chain(
    values: Optional[list[AttributionStep | dict]],
) -> list[AttributionStep]:
    return [
        value
        if isinstance(value, AttributionStep)
        else AttributionStep.model_validate(value)
        for value in values or []
    ]


def _coerce_source_supports(
    values: Optional[list[SourceSupport | dict]],
) -> list[SourceSupport]:
    return [
        value
        if isinstance(value, SourceSupport)
        else SourceSupport.model_validate(value)
        for value in values or []
    ]


def _range_from_date_text(
    raw_value: object,
    *,
    basis: EvidenceBasis,
    confidence: float,
    source_document_id: str,
    source_page_label: Optional[str] = None,
    source_field: Optional[str] = None,
    source_excerpt: Optional[str] = None,
    source_char_start: Optional[int] = None,
    source_char_end: Optional[int] = None,
    rationale: Optional[str] = None,
) -> Optional[EvidentialDateRange]:
    """Convert common document/claim date strings to bounded ranges."""
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None

    circa = bool(re.search(r"\b(ca\.?|circa|c\.)\b", raw, flags=re.IGNORECASE))
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        date = match.group(0)
        return EvidentialDateRange(
            start=date,
            end=date,
            circa=circa,
            precision="day",
            label=raw,
            basis=basis,
            confidence=confidence,
            source_document_id=source_document_id,
            source_page_label=source_page_label,
            source_field=source_field,
            source_excerpt=source_excerpt,
            source_char_start=source_char_start,
            source_char_end=source_char_end,
            rationale=rationale,
        )

    match = re.search(r"(\d{4})-(\d{2})", raw)
    if match:
        year, month = match.groups()
        return EvidentialDateRange(
            start=f"{year}-{month}-01",
            end=f"{year}-{month}-31",
            circa=circa,
            precision="month",
            label=raw,
            basis=basis,
            confidence=confidence,
            source_document_id=source_document_id,
            source_page_label=source_page_label,
            source_field=source_field,
            source_excerpt=source_excerpt,
            source_char_start=source_char_start,
            source_char_end=source_char_end,
            rationale=rationale,
        )

    match = re.search(r"\b(\d{4})\b", raw)
    if match:
        year = match.group(1)
        return EvidentialDateRange(
            start=f"{year}-01-01",
            end=f"{year}-12-31",
            circa=circa,
            precision="year",
            label=raw,
            basis=basis,
            confidence=confidence,
            source_document_id=source_document_id,
            source_page_label=source_page_label,
            source_field=source_field,
            source_excerpt=source_excerpt,
            source_char_start=source_char_start,
            source_char_end=source_char_end,
            rationale=rationale,
        )
    return None


def _metadata_value(metadata: dict, keys: tuple[str, ...]) -> tuple[object, str] | None:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value, key
    return None


def _first_source_date_anchor(
    db: Database,
    source_document_id: str,
) -> tuple[object, str] | None:
    from fichero.models import Document

    doc = db.get(Document, source_document_id)
    if doc is None:
        _warn_missing_source_document(source_document_id, context="evidential date")
        return None

    source_metadata = doc.source_metadata or {}
    if isinstance(source_metadata, dict):
        value = _metadata_value(
            source_metadata,
            ("issued", "created", "date", "year", "publication_date", "creation_date"),
        )
        if value is not None:
            raw, key = value
            return raw, f"source_metadata.{key}"

    for index, step in enumerate(doc.provenance_chain or []):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").lower()
        if action in {"scanned", "accessed", "downloaded", "digitized", "digitised"}:
            continue
        if step.get("date") not in (None, ""):
            return step["date"], f"provenance_chain[{index}].date"

    return None


def _first_source_place_anchor(
    db: Database,
    source_document_id: str,
) -> tuple[object, str] | None:
    from fichero.models import Document

    doc = db.get(Document, source_document_id)
    if doc is None:
        _warn_missing_source_document(source_document_id, context="evidential place")
        return None

    for field_name, metadata in (
        ("source_metadata", doc.source_metadata or {}),
        ("metadata", doc.metadata or {}),
    ):
        if not isinstance(metadata, dict):
            continue
        value = _metadata_value(
            metadata,
            ("place", "location", "origin_place", "publication_place", "region"),
        )
        if value is not None:
            raw, key = value
            return raw, f"{field_name}.{key}"

    for index, step in enumerate(doc.provenance_chain or []):
        if isinstance(step, dict) and step.get("location") not in (None, ""):
            return step["location"], f"provenance_chain[{index}].location"

    return None


def _first_source_recorder_anchor(
    db: Database,
    source_document_id: str,
) -> tuple[str | None, str, str] | None:
    from fichero.models import Document

    doc = db.get(Document, source_document_id)
    if doc is None:
        _warn_missing_source_document(source_document_id, context="source recorder")
        return None

    for index, step in enumerate(doc.provenance_chain or []):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").lower()
        if action in {"scanned", "accessed", "downloaded", "digitized", "digitised"}:
            continue
        actor = step.get("actor")
        label = action or step.get("label") or "source provenance"
        if actor or action:
            return (
                str(actor) if actor else None,
                str(label),
                f"provenance_chain[{index}]",
            )
    return None


def _build_attribution_chain(
    db: Database,
    *,
    speaker_name: Optional[str],
    source_document_id: str,
    source_page_label: Optional[str],
    source_excerpt: Optional[str],
    provider: Optional[str],
    model: Optional[str],
    explicit_chain: Optional[list[AttributionStep | dict]],
) -> list[AttributionStep]:
    chain = _coerce_attribution_chain(explicit_chain)
    if chain:
        return chain

    order = 0
    if speaker_name:
        chain.append(
            AttributionStep(
                role=AttributionRole.asserter,
                name=speaker_name,
                basis=EvidenceBasis.asserted,
                confidence=0.65,
                source_excerpt=source_excerpt,
                order=order,
            )
        )
        order += 1
    recorder = _first_source_recorder_anchor(db, source_document_id)
    if recorder is not None:
        name, label, source_field = recorder
        chain.append(
            AttributionStep(
                role=AttributionRole.recorder,
                name=name,
                label=label,
                basis=EvidenceBasis.source_anchored,
                confidence=0.55,
                source_field=source_field,
                order=order,
            )
        )
        order += 1
    chain.append(
        AttributionStep(
            role=AttributionRole.source_document,
            document_id=source_document_id,
            label=source_page_label,
            basis=EvidenceBasis.source_anchored,
            confidence=0.7,
            source_field="KnowledgeClaim.source_document_id",
            order=order,
        )
    )
    order += 1
    if provider or model:
        chain.append(
            AttributionStep(
                role=AttributionRole.extractor,
                name=provider,
                label=model,
                basis=EvidenceBasis.inferred,
                confidence=0.5,
                order=order,
            )
        )
    return chain


def derive_evidential_dimensions(
    db: Database,
    *,
    source_document_id: str,
    source_page_label: Optional[str],
    source_excerpt: Optional[str],
    source_char_start: Optional[int],
    source_char_end: Optional[int],
    source_bbox: Optional[list[float]],
    confidence: float,
    asserted_date_values: Optional[list[EvidentialDateRange | dict]] = None,
    asserted_place_values: Optional[list[EvidentialPlace | dict]] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    time_precision: Optional[str] = None,
    claim_location: Optional[str] = None,
    claim_geo: Optional[GeoPoint] = None,
    attribution_chain: Optional[list[AttributionStep | dict]] = None,
    speaker_name: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[
    list[EvidentialDateRange],
    list[EvidentialPlace],
    list[AttributionStep],
    SourceSupport,
]:
    date_values = _coerce_date_values(asserted_date_values)
    if not date_values and (time_start or time_end):
        date_values.append(
            EvidentialDateRange(
                start=time_start,
                end=time_end or time_start,
                precision=time_precision,
                basis=EvidenceBasis.asserted,
                confidence=confidence,
                source_document_id=source_document_id,
                source_page_label=source_page_label,
                source_excerpt=source_excerpt,
                source_char_start=source_char_start,
                source_char_end=source_char_end,
            )
        )
    if not date_values:
        anchor = _first_source_date_anchor(db, source_document_id)
        if anchor is not None:
            raw, source_field = anchor
            date_value = _range_from_date_text(
                raw,
                basis=EvidenceBasis.source_anchored,
                confidence=0.55,
                source_document_id=source_document_id,
                source_page_label=source_page_label,
                source_field=source_field,
                source_excerpt=source_excerpt,
                rationale=(
                    "Claim text lacks an asserted date; bounded from source "
                    "document metadata."
                ),
            )
            if date_value is not None:
                date_value.open_start = True
                date_values.append(date_value)

    place_values = _coerce_place_values(asserted_place_values)
    if not place_values and claim_location:
        place_values.append(
            EvidentialPlace(
                label=claim_location,
                geometry_type=(
                    PlaceGeometryType.point if claim_geo else PlaceGeometryType.unknown
                ),
                lat=claim_geo.lat if claim_geo else None,
                lon=claim_geo.lon if claim_geo else None,
                precision_m=claim_geo.precision_m if claim_geo else None,
                basis=EvidenceBasis.asserted,
                confidence=confidence,
                source_document_id=source_document_id,
                source_page_label=source_page_label,
                source_excerpt=source_excerpt,
            )
        )
    if not place_values:
        anchor = _first_source_place_anchor(db, source_document_id)
        if anchor is not None:
            raw, source_field = anchor
            label = str(raw).strip()
            if label:
                place_values.append(
                    EvidentialPlace(
                        label=label,
                        geometry_type=PlaceGeometryType.region,
                        basis=EvidenceBasis.source_anchored,
                        confidence=0.5,
                        source_document_id=source_document_id,
                        source_page_label=source_page_label,
                        source_field=source_field,
                        source_excerpt=source_excerpt,
                        rationale=(
                            "Claim text lacks an asserted place; derived from "
                            "source document place metadata."
                        ),
                    )
                )

    chain = _build_attribution_chain(
        db,
        speaker_name=speaker_name,
        source_document_id=source_document_id,
        source_page_label=source_page_label,
        source_excerpt=source_excerpt,
        provider=provider,
        model=model,
        explicit_chain=attribution_chain,
    )
    support = SourceSupport(
        source_document_id=source_document_id,
        source_page_label=source_page_label,
        source_excerpt=source_excerpt,
        source_char_start=source_char_start,
        source_char_end=source_char_end,
        source_bbox=source_bbox,
        support_basis=EvidenceBasis.asserted,
        support_confidence=confidence,
        date_values=date_values,
        place_values=place_values,
        attribution_chain=chain,
    )
    return date_values, place_values, chain, support


def _same_structured_claim(a: KnowledgeClaim, b: KnowledgeClaim) -> bool:
    if set(a.entity_ids) != set(b.entity_ids):
        return False

    a_svo = (
        a.svo_subject or a.subject_canonical,
        a.svo_verb or a.predicate_canonical or a.predicate_verb,
        a.svo_object or a.object_phrase,
    )
    b_svo = (
        b.svo_subject or b.subject_canonical,
        b.svo_verb or b.predicate_canonical or b.predicate_verb,
        b.svo_object or b.object_phrase,
    )
    if all(a_svo) and all(b_svo):
        a_key = _normalized_claim_svo_key(*a_svo)
        b_key = _normalized_claim_svo_key(*b_svo)
        return a_key is not None and a_key == b_key

    from difflib import SequenceMatcher

    return SequenceMatcher(None, a.text, b.text).ratio() >= 0.92


def _same_claim_identity(
    prior: KnowledgeClaim,
    *,
    entity_ids: set[str],
    text: str,
    svo_subject: str | None,
    svo_verb: str | None,
    svo_object: str | None,
) -> bool:
    """Return True when an incoming save would duplicate ``prior``."""
    if set(prior.entity_ids) != entity_ids:
        return False

    incoming_key = _normalized_claim_svo_key(svo_subject, svo_verb, svo_object)
    prior_key = _normalized_claim_svo_key(
        prior.svo_subject or prior.subject_canonical,
        prior.svo_verb or prior.predicate_canonical or prior.predicate_verb,
        prior.svo_object or prior.object_phrase,
    )
    if incoming_key is not None and prior_key is not None:
        return incoming_key == prior_key

    from difflib import SequenceMatcher

    return SequenceMatcher(None, prior.text, text).ratio() >= 0.9


def _find_cross_source_canonical_claim(
    db: Database,
    claim: KnowledgeClaim,
) -> Optional[KnowledgeClaim]:
    """Find an existing claim from another source that this claim corroborates."""
    for prior in db.all(KnowledgeClaim):
        if prior.source_document_id == claim.source_document_id:
            continue
        if _same_structured_claim(prior, claim):
            return prior
    return None


def _repoint_claim_entity_references(
    db: Database,
    *,
    duplicate_ids: set[str],
    survivor_id: str,
) -> list[str]:
    """Replace duplicate entity references in claims before deleting rows."""
    if not duplicate_ids:
        return []

    scalar_fields = (
        "subject_entity_id",
        "speaker_entity_id",
        "subject_of_inquiry_entity_id",
        "scribe_entity_id",
        "editor_entity_id",
    )
    repointed_claim_ids: list[str] = []

    for claim in db.query(KnowledgeClaim):
        changed = False

        old_ids = claim.entity_ids or []
        if any(entity_id in duplicate_ids for entity_id in old_ids):
            new_ids = [
                survivor_id if entity_id in duplicate_ids else entity_id
                for entity_id in old_ids
            ]
            seen: set[str] = set()
            claim.entity_ids = [
                entity_id
                for entity_id in new_ids
                if not (entity_id in seen or seen.add(entity_id))
            ]
            changed = True

        for field_name in scalar_fields:
            if getattr(claim, field_name, None) in duplicate_ids:
                setattr(claim, field_name, survivor_id)
                changed = True

        if changed:
            db.save(claim)
            repointed_claim_ids.append(claim.id)

    return repointed_claim_ids


def _support_key(
    support: SourceSupport,
) -> tuple[str, str | None, int | None, int | None]:
    return (
        support.source_document_id,
        support.source_page_label,
        support.source_char_start,
        support.source_char_end,
    )


def _merge_unique_by_id(existing: list, incoming: list) -> list:
    seen = {getattr(item, "id", None) for item in existing}
    merged = list(existing)
    for item in incoming:
        item_id = getattr(item, "id", None)
        if item_id not in seen:
            merged.append(item)
            seen.add(item_id)
    return merged


def _merge_corroborating_claim(
    db: Database,
    canonical: KnowledgeClaim,
    incoming: KnowledgeClaim,
) -> None:
    """Fold a cross-source duplicate into the canonical claim's support set."""
    existing_support_keys = {
        _support_key(support) for support in canonical.source_supports
    }
    for support in incoming.source_supports:
        if _support_key(support) not in existing_support_keys:
            canonical.source_supports.append(support)
            existing_support_keys.add(_support_key(support))

    source_ids = {
        canonical.source_document_id,
        incoming.source_document_id,
        *canonical.source_ids,
        *incoming.source_ids,
        *canonical.corroborating_source_ids,
        *incoming.corroborating_source_ids,
        *(support.source_document_id for support in canonical.source_supports),
    }
    canonical.source_ids = sorted(source_ids - {canonical.source_document_id})
    canonical.corroborating_source_ids = sorted(source_ids)
    canonical.corroboration_count = len(source_ids)
    canonical.weighted_corroboration_count = _weighted_corroboration_count(
        db,
        source_ids,
    )

    page_labels = {
        label
        for label in [
            canonical.source_page_label,
            incoming.source_page_label,
            *canonical.source_page_labels,
            *incoming.source_page_labels,
        ]
        if label
    }
    canonical.source_page_labels = sorted(page_labels)
    canonical.date_values = _merge_unique_by_id(canonical.date_values, incoming.date_values)
    canonical.place_values = _merge_unique_by_id(canonical.place_values, incoming.place_values)
    canonical.attribution_chain = _merge_unique_by_id(
        canonical.attribution_chain,
        incoming.attribution_chain,
    )
    bonus = min(0.2, 0.05 * max(0, canonical.corroboration_count - 1))
    canonical.confidence = min(
        1.0,
        max(canonical.confidence, incoming.confidence) + bonus,
    )
    canonical.confidence_source = "corroboration"
    canonical.evidential_confidence = canonical.confidence
    canonical.evidential_confidence_source = "corroboration"
    db.save(canonical)

    link_id = f"corroborates:{canonical.id}:{incoming.source_document_id}"
    if db.get(KnowledgeClaimLink, link_id) is None:
        db.save(
            KnowledgeClaimLink(
                id=link_id,
                claim_id=canonical.id,
                related_claim_id=canonical.id,
                relation_type=ClaimRelationType.corroborates,
                link_quality=incoming.confidence,
                evidence=incoming.source_excerpt,
                metadata={
                    "source_document_id": incoming.source_document_id,
                    "source_page_label": incoming.source_page_label,
                    "self_link": True,
                    "reason": "Canonical claim has an additional corroborating source support.",
                },
            )
        )


def _record_source_page(
    db: Database,
    entity: "KnowledgeEntity",
    source_document_id: Optional[str],
) -> None:
    """Append ``source_document_id`` to the entity's per-page scope (#1562).

    Idempotent: only persists when the id is truthy and not already present,
    so an existing entity accumulates each page it appears on without dupes.
    """
    if not source_document_id:
        return
    existing_ids = list(entity.source_document_ids or [])
    if source_document_id in existing_ids:
        return
    existing_ids.append(source_document_id)
    entity.source_document_ids = existing_ids
    db.save(entity)


@_serialized_entity_upsert
def upsert_entity(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
    source_document_id: Optional[str] = None,
) -> str | None:
    """Look up entity by ``(canonical_name, entity_type)``; create if missing.

    Three-stage match (#897 → #899 Phase B):
    1. Exact ``(canonical_name, entity_type)`` lookup — covers stable
       names like "Eugenio Córdoba" repeated across pages.
    2. **Embedding cosine** via LanceDB (`kg.entity_vectors`) over
       same-type entities. Catches semantic divergence in noun
       phrases ("Racial Economic Exclusion" vs "Race and Economic
       Marginalization") that pure SequenceMatcher misses. Cosine
       >= 0.92 → auto-merge ONLY IF a lexical-agreement precision
       gate also passes (#1907 — otherwise routed to review so
       "San Pablo"/"San Juan" don't collapse); 0.75–0.92 → logged
       for the review gate (#377); <0.75 → fall through.
    3. SequenceMatcher fallback for the case where vectors aren't
       available yet (table empty, model failed to load, etc.). Keeps
       the 0.0.2 behaviour as a floor.

    On a successful merge (#2 or #3), the new ``canonical_name`` and
    ``aliases`` fold into the existing entity's ``aliases``. On a
    create, the new entity is indexed in LanceDB so future lookups
    can find it.

    Returns the entity ID. Idempotent on the exact path; the fuzzy
    paths preserve surface-form evidence via the aliases list.
    """
    resolved = _apply_entity_resolution_rules(db, canonical_name, entity_type)
    if resolved is None:
        return None
    canonical_name, entity_type = resolved

    existing = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if existing:
        _record_source_page(db, existing[0], source_document_id)  # #1562
        return existing[0].id

    # Stage 1.5 — Type-conflict detector (#1114 issue 1)
    # ----------------------------------------------------
    # The exact lookup keys on (canonical_name, entity_type), so
    # "Atrató River" entered first as `concept` and then later as
    # `location` produced two rows. For a deduplicated KG, a river
    # is a `location`; the `concept` row is the catchall the LLM
    # falls back to when section classification fails.
    #
    # Detection: if any other-type row exists with the same canonical
    # name, decide whether to:
    #   (a) promote the existing row's type if it's the catchall
    #       `concept` and the new claim names a more specific type
    #       (person / location / organization / event), OR
    #   (b) leave both rows and log a warning — type ambiguity that
    #       might be legitimate (e.g., "Mexico City" the location vs
    #       an event titled "Mexico City").
    #
    # We intentionally don't auto-merge in case (b); a false-positive
    # cross-type merge would silently collapse distinct entities and
    # users would have no audit trail. The warning + an EntityMergeAudit
    # candidate row (see future work) is the safer path.
    other_type = db.query(KnowledgeEntity, canonical_name=canonical_name)
    if other_type:
        prior = other_type[0]
        prior_type_val = (
            prior.entity_type.value
            if hasattr(prior.entity_type, "value")
            else str(prior.entity_type)
        )
        new_type_val = (
            entity_type.value
            if hasattr(entity_type, "value")
            else str(entity_type)
        )
        # `concept` is the catchall — promote to the more specific type.
        if prior_type_val == "concept" and new_type_val != "concept":
            logger.info(
                "upsert_entity: type-conflict promotion %r %s → %s (#1114)",
                canonical_name, prior_type_val, new_type_val,
            )
            prior.entity_type = entity_type
            db.save(prior)
            _record_source_page(db, prior, source_document_id)  # #1562
            return prior.id
        # Symmetric: existing row is specific, new request is `concept`.
        # Keep the existing specific type; just return the same id.
        if new_type_val == "concept" and prior_type_val != "concept":
            logger.info(
                "upsert_entity: ignoring concept-typed upsert for "
                "existing specific entity %r (%s) (#1114)",
                canonical_name, prior_type_val,
            )
            _record_source_page(db, prior, source_document_id)  # #1562
            return prior.id
        # Both types are specific (location vs event, etc.) — log and
        # fall through to create a new row. Human review can later
        # decide whether to collapse them.
        logger.warning(
            "upsert_entity: ambiguous type for %r — existing=%s, "
            "new=%s; creating a second row (#1114). Review the merge "
            "candidate via the review queue.",
            canonical_name, prior_type_val, new_type_val,
        )

    # Stage 1.7 — Admin-qualifier dedup (#1114 issue 2)
    # --------------------------------------------------
    # Catch "Chocó" vs "Chocó department" cases that the existing
    # SequenceMatcher / token-set fuzzy match misses (score 0.5 for
    # one-token-in-two-tokens) before paying the embedding-stage
    # cost. Deterministic, cheap, no model variance — runs even when
    # vectors are unavailable.
    same_type_for_admin = db.query(
        KnowledgeEntity, entity_type=entity_type,
    )
    for ent in same_type_for_admin:
        if _admin_qualifier_match(canonical_name, ent.canonical_name):
            logger.info(
                "upsert_entity: admin-qualifier merge %r → %s (%r) (#1114)",
                canonical_name, ent.id, ent.canonical_name,
            )
            # Fold the new surface form into the existing entity's
            # aliases so the original phrasing is preserved.
            seen_folded: dict[str, str] = {}
            for surface in list(ent.aliases or []) + [canonical_name] + list(aliases or []):
                if not surface or not surface.strip():
                    continue
                key = surface.strip().casefold()
                if key not in seen_folded:
                    seen_folded[key] = surface.strip()
            canonical_key = ent.canonical_name.strip().casefold()
            ent.aliases = sorted(
                v for k, v in seen_folded.items() if k != canonical_key
            )
            db.save(ent)
            _record_source_page(db, ent, source_document_id)  # #1562
            return ent.id

    # Stage 2: embedding cosine. Lazy-imports the model on first call;
    # subsequent calls are free. Failures fall through to stage 3.
    matched: Optional[KnowledgeEntity] = None
    # _pending_review: (survivor_id, score, survivor_name) when we hit
    # the review band; consumed AFTER stage 4 creates the new entity
    # so the EntityMatchCandidate row references a real candidate id.
    _pending_review: Optional[tuple[str, float, str]] = None
    try:
        from fichero.kg import entity_vectors

        hits = entity_vectors.find_similar(
            db=db,
            canonical_name=canonical_name,
            entity_type=entity_type,
            description=description,
            top_k=3,
        )
        if hits:
            best_id, best_score, best_name = hits[0]
            if best_score >= entity_vectors.AUTO_MERGE_THRESHOLD and _lexical_agreement(
                canonical_name, best_name
            ):
                # Precision gate passed (#1907): cosine is in the
                # auto-merge band AND the surface forms agree lexically
                # (accent/spacing variant or shared content tokens).
                matched = db.get(KnowledgeEntity, best_id)
                if matched is not None:
                    logger.info(
                        "upsert_entity: embedding auto-merge %r → %s (%r, cosine=%.3f)",
                        canonical_name, best_id, best_name, best_score,
                    )
            elif best_score >= entity_vectors.AUTO_MERGE_THRESHOLD:
                # Precision gate FAILED (#1907): cosine alone would
                # merge, but the surface forms materially differ
                # ("San Pablo" vs "San Juan"). Embedding similarity is
                # not enough to collapse distinct entities, so route to
                # the human review queue instead of auto-merging.
                logger.info(
                    "upsert_entity: embedding cosine %.3f for %r ~ %r but "
                    "lexical agreement low — routing to review instead of "
                    "auto-merge (#1907)",
                    best_score, canonical_name, best_name,
                )
                _pending_review = (best_id, best_score, best_name)
            elif best_score >= entity_vectors.REVIEW_THRESHOLD:
                # Mid-band: surface for the human review queue (#377 /
                # #899 Phase D). We DON'T auto-merge here — false
                # positives would silently collapse distinct entities.
                # Defer the EntityMatchCandidate write until after we
                # know the new entity's id (stage 4 below).
                logger.info(
                    "upsert_entity: embedding flagged-for-review "
                    "%r ~ %s (%r, cosine=%.3f) — queued for human review",
                    canonical_name, best_id, best_name, best_score,
                )
                _pending_review = (best_id, best_score, best_name)
    except Exception as exc:
        # Vector backend unhealthy — don't take down the catalogue.
        logger.warning("upsert_entity: embedding stage failed: %s", exc)

    # Stage 3: SequenceMatcher floor. Only run when embeddings didn't
    # decide a merge; mirrors the 0.0.2 behaviour as a safety net.
    if matched is None:
        same_type = db.query(KnowledgeEntity, entity_type=entity_type)
        matched = _fuzzy_match_existing(same_type, canonical_name)
        if matched is not None:
            logger.info(
                "upsert_entity: SequenceMatcher fallback merged "
                "%r → %s (%r)",
                canonical_name, matched.id, matched.canonical_name,
            )

    if matched is not None:
        # Fold the new surface form + aliases into the existing entity.
        # Case-fold for dedup so "Artisanal mining" and "artisanal mining"
        # don't both end up in the aliases list (#986 — Daniel saw
        # "Artisanal mining" + alias "artisanal mining" on the same
        # entity). We keep the FIRST-seen surface form per case-folded
        # key (typically the better-capitalised variant from the source
        # text).
        seen_folded: dict[str, str] = {}
        for surface in list(matched.aliases or []) + [canonical_name] + list(aliases or []):
            if not surface or not surface.strip():
                continue
            key = surface.strip().casefold()
            if key not in seen_folded:
                seen_folded[key] = surface.strip()
        # Drop the canonical itself + any case variant of it.
        canonical_key = matched.canonical_name.strip().casefold()
        matched.aliases = sorted(
            v for k, v in seen_folded.items() if k != canonical_key
        )
        db.save(matched)
        # Refresh the vector to reflect the new alias set — the
        # encoded description grows with each merged occurrence so
        # future matches keep improving.
        try:
            from fichero.kg import entity_vectors

            entity_vectors.index_entity(
                db=db,
                entity_id=matched.id,
                entity_type=entity_type,
                canonical_name=matched.canonical_name,
                description=matched.description,
            )
        except Exception as exc:
            # #2507: don't swallow silently — a stale alias-merge vector
            # degrades future fuzzy matches. Log loudly like the new-entity
            # index path below; the catalogue stays up either way.
            logger.warning(
                "upsert_entity: failed to refresh merged entity vector "
                "(id=%s): %s",
                matched.id,
                exc,
            )
        _record_source_page(db, matched, source_document_id)  # #1562
        return matched.id

    # Stage 4: create a brand-new entity + index its vector.
    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
        source_document_ids=[source_document_id] if source_document_id else [],  # #1562
    )
    db.save(entity)

    # Stage 4.5 — Race recovery (#1121)
    # ---------------------------------
    # Between Stage 1's "no existing row" lookup and this Stage 4 save,
    # a concurrent caller can hit Stages 1-4 with the same
    # (canonical_name, entity_type) and also create a new row. Both
    # writes succeed (different UUIDs, no PK conflict to upsert
    # against), leaving silent duplicates. The entity inspector then
    # aggregates against ONE id and misses claims attached to the
    # other.
    #
    # Recovery: re-query for siblings with the same canonical_name +
    # entity_type. If more than one row exists, keep the OLDEST
    # (lowest created_at) as canonical, fold every duplicate's
    # aliases + canonical_name into the survivor's aliases, then
    # delete the duplicates. Idempotent — if two concurrent callers
    # both reconcile, they converge on the same survivor and the
    # second cleanup is a no-op.
    #
    # The race window remains microscopic (DuckDB serializes writes
    # on a single connection; cross-thread sharing the same db_manager
    # cache is the realistic exposure), so the post-write re-query
    # almost always returns just our row. The cost is one extra
    # query per Stage 4 entity creation — negligible compared to the
    # LLM extraction cost upstream.
    siblings = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if len(siblings) > 1:
        siblings.sort(key=lambda e: e.created_at)
        survivor = siblings[0]
        duplicate_ids = {dup.id for dup in siblings[1:]}
        repointed_claim_ids = _repoint_claim_entity_references(
            db,
            duplicate_ids=duplicate_ids,
            survivor_id=survivor.id,
        )
        # Aliases-fold helper inline so it's local to the race path.
        seen_folded = {a.strip().casefold(): a.strip()
                       for a in (survivor.aliases or [])
                       if a and a.strip()}
        canonical_key = survivor.canonical_name.strip().casefold()
        for dup in siblings[1:]:
            for surface in (
                [dup.canonical_name] + list(dup.aliases or [])
            ):
                if not surface or not surface.strip():
                    continue
                key = surface.strip().casefold()
                if key != canonical_key and key not in seen_folded:
                    seen_folded[key] = surface.strip()
            db.delete(dup)
        survivor.aliases = sorted(seen_folded.values())
        db.save(survivor)
        logger.warning(
            "upsert_entity: race-recovery merged %d duplicate(s) of "
            "%r → %s and repointed %d claim(s) (#1121)",
            len(siblings) - 1, canonical_name, survivor.id, len(repointed_claim_ids),
        )
        # The caller wants the surviving id, not the one we just
        # created (which we just deleted above if we lost the race).
        _record_source_page(db, survivor, source_document_id)  # #1562
        return survivor.id

    try:
        from fichero.kg import entity_vectors

        entity_vectors.index_entity(
            db=db,
            entity_id=entity.id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            description=description,
        )
    except Exception as exc:
        logger.warning("upsert_entity: failed to index new entity vector: %s", exc)

    # Stage 5: write the EntityMatchCandidate row when stage 2 hit the
    # review band. The survivor is the existing entity (higher claim
    # count typically, definitely the older one); the candidate is the
    # newly-created entity. Reviewer decides later via the review
    # queue API. (#899 Phase D / #377)
    if _pending_review is not None:
        survivor_id, score, survivor_name = _pending_review
        try:
            from fichero.knowledge_models import (
                EntityMatchCandidate,
                PendingMatchMethod,
                PendingMatchState,
            )
            db.save(EntityMatchCandidate(
                survivor_entity_id=survivor_id,
                candidate_entity_id=entity.id,
                score=float(score),
                method=PendingMatchMethod.embedding_cosine,
                state=PendingMatchState.pending,
                reason=(
                    f"embedding cosine {score:.3f} between "
                    f"{canonical_name!r} and {survivor_name!r}"
                ),
            ))
        except Exception as exc:
            logger.warning("upsert_entity: failed to queue review candidate: %s", exc)

    return entity.id


# =============================================================================
# #1123 Phase D — heuristic attribution detection
# =============================================================================
# Cheap regex / string-shape detectors that derive attribution fields from
# the existing claim text + source excerpt — no extra LLM calls. Each
# detector returns ``None`` when it can't tell (honest absence over
# guessed mapping). The save_claim wrapper below applies them automatically
# unless the caller passed an explicit value.

# Reporting verbs that signal speech / testimony attribution. Detect on
# the predicate_verb (not on free-form text) so a sentence that merely
# *mentions* the verb in passing ("she said no when the deed was filed")
# doesn't trigger quotation_kind=verbatim on an unrelated claim.
_REPORTING_VERBS = {
    "said", "stated", "declared", "asserted", "claimed", "testified",
    "petitioned", "reported", "argued", "wrote", "denied",
    "testified about", "testified that",
}

# Smart quotes + double-angle + straight + Spanish low-9 / German quotes.
_QUOTE_CHARS_RE = re.compile(r'["“”‘’«»„‚]')

# "<Speaker> said/testified/declared ...". The name capture group accepts
# 1-4 capitalised tokens or a clearly-marked title-phrase ("the witness X").
_SPEAKER_BEFORE_RE = re.compile(
    r"(?:^|[\.\n;]\s*)"
    r"(?P<speaker>(?:the\s+)?(?:witness|petitioner|deponent|scribe|"
    r"alcalde|cabildo|notary|don|doña|señor|señora|king|queen|"
    r"viceroy|judge|priest|presbyter)?\s*"
    r"(?:[A-Z][\wÀ-ÖØ-öø-ÿ\.’']*\s*){1,4})"
    r"\s+(?:said|stated|declared|asserted|claimed|testified|"
    r"petitioned|reported|argued|wrote|denied)\b",
    re.IGNORECASE,
)

# "according to <Speaker>", "as stated by <Speaker>"
_SPEAKER_ACCORDING_RE = re.compile(
    r"(?:according to|as stated by|per the testimony of|in the words of)\s+"
    r"(?P<speaker>(?:the\s+)?[A-Z][\wÀ-ÖØ-öø-ÿ\.’']*"
    r"(?:\s+[A-Z][\wÀ-ÖØ-öø-ÿ\.’']*){0,3})",
    re.IGNORECASE,
)

# "addressed to / to the <Audience>" — for petitions, decrees, letters.
# Restrict to capitalised audiences (institutions / titles) so generic
# "to the place" prepositional phrases don't fire.
_AUDIENCE_RE = re.compile(
    r"(?:addressed\s+to|directed\s+to|to\s+the)\s+"
    r"(?P<audience>(?:the\s+)?"
    r"(?:Cabildo|Audiencia|Crown|King|Queen|Viceroy|Court|Tribunal|"
    r"Council|Assembly|Congress|Senate|Governor|Alcalde|Judge|"
    r"Bishop|Archbishop|Inquisition)"
    r"(?:\s+of\s+[A-Z][\wÀ-ÖØ-öø-ÿ\.’']*"
    r"(?:\s+[A-Z][\wÀ-ÖØ-öø-ÿ\.’']*)*)?)",
)


def _detect_quotation_kind(
    predicate_verb: str | None,
    source_excerpt: str | None,
) -> QuotationKind | None:
    """Heuristic: verbatim if quotes-around-the-claim + reporting verb,
    indirect if reporting verb without quotes, None otherwise.

    Conservative on purpose. We'd rather leave the field null than
    claim something is verbatim that isn't — the inspector treats
    verbatim as a warrant-strength signal, and a false positive
    propagates downstream credibility.
    """
    if not predicate_verb:
        return None
    verb_norm = predicate_verb.lower().strip()
    is_reporting = verb_norm in _REPORTING_VERBS or any(
        verb_norm.startswith(v + " ") for v in _REPORTING_VERBS
    )
    if not is_reporting:
        return None
    has_quotes = bool(_QUOTE_CHARS_RE.search(source_excerpt or ""))
    return QuotationKind.verbatim if has_quotes else QuotationKind.indirect


def _detect_speaker(
    claim_text: str | None,
    source_excerpt: str | None,
) -> str | None:
    """Pull a speaker name from "X said" / "according to X" patterns.

    Searches the source_excerpt first (where the original phrasing lives),
    then falls back to the composed claim text. Caps length to 80 chars
    so a runaway match doesn't pollute the field.
    """
    for blob in (source_excerpt, claim_text):
        if not blob:
            continue
        for pat in (_SPEAKER_ACCORDING_RE, _SPEAKER_BEFORE_RE):
            m = pat.search(blob)
            if m:
                speaker = m.group("speaker").strip(" .,;:'\"’")
                # Reject too-short (likely a stray pronoun match) and
                # too-long (likely the whole sentence) extractions.
                if 2 <= len(speaker) <= 80:
                    return speaker
    return None


def _detect_audience(
    claim_text: str | None,
    source_excerpt: str | None,
) -> str | None:
    """Pull "the Cabildo of Popayán" / "the Audiencia" type addressees
    from the source text. Limited to capitalised institutional nouns;
    a generic "to the place" doesn't match.
    """
    for blob in (source_excerpt, claim_text):
        if not blob:
            continue
        m = _AUDIENCE_RE.search(blob)
        if m:
            aud = m.group("audience").strip(" .,;:")
            if 3 <= len(aud) <= 80:
                return aud
    return None


def save_claim(
    db: Database,
    text: str,
    source_document_id: str,
    entity_ids: Optional[list[str]] = None,
    source_excerpt: Optional[str] = None,
    source_page_label: Optional[str] = None,
    claim_type: ClaimType = ClaimType.fact,
    confidence: float = 0.5,
    metadata: Optional[dict] = None,
    epistemic_status: Optional[EpistemicStatus] = None,
    source_char_start: Optional[int] = None,
    source_char_end: Optional[int] = None,
    source_bbox: Optional[list[float]] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
    time_precision: Optional[str] = None,
    subject_canonical: Optional[str] = None,
    subject_entity_id: Optional[str] = None,
    predicate_verb: Optional[str] = None,
    object_phrase: Optional[str] = None,
    # #730 SVO aliases. Callers (extractors) pass these alongside the legacy
    # subject_canonical/predicate_verb/object_phrase names; forward them to the
    # model's svo_* fields, defaulting to the legacy values when not supplied so
    # both naming sets stay consistent on every written claim.
    svo_subject: Optional[str] = None,
    svo_verb: Optional[str] = None,
    svo_object: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    language: Optional[str] = None,
    # --- #1123 Phase D additions ---
    # All optional; auto-derive from claim text + source excerpt when
    # not passed. Callers who already have explicit values (e.g. a
    # later structured-extraction pass that detects speakers via LLM)
    # can override the heuristic.
    source_language: Optional[str] = None,
    quotation_kind: Optional[QuotationKind] = None,
    speaker_name: Optional[str] = None,
    audience: Optional[str] = None,
    confidence_origin: Optional[str] = None,
    claim_location: Optional[str] = None,
    claim_geo: Optional[GeoPoint] = None,
    date_values: Optional[list[EvidentialDateRange | dict]] = None,
    place_values: Optional[list[EvidentialPlace | dict]] = None,
    attribution_chain: Optional[list[AttributionStep | dict]] = None,
    source_supports: Optional[list[SourceSupport | dict]] = None,
    claim_recorded_at: Optional[str] = None,
) -> str | None:
    """Save a `KnowledgeClaim` row. Returns the claim ID.

    Claims are document-scoped textual assertions linked to entities via
    ``entity_ids``. Date-style claims (no canonical entity to dedup) pass
    an empty list for ``entity_ids``; the normalized date lives in
    ``metadata['date_normalized']``.

    ``source_page_label`` lands on the dedicated ``KnowledgeClaim`` field
    so cross-doc views and graph traversal can answer "which page of
    which document mentions this entity?"

    ``epistemic_status`` records the LLM-assigned confidence label
    (tentative/confirmed/rejected) so the inspector can filter and
    badge claims. None means leave the default on the model.

    Defense-in-depth dedup (#896): if a claim already exists for the
    same ``(source_document_id, source_page_label, entity_ids set)``
    with text overlap >= 90%, return that claim's ID instead of
    writing a new row. The Davidson ×6 incident landed before this
    check existed; per the issue, the upstream fan-out gets fixed
    separately but this guard means a partial regression can't
    repopulate the same six rows.

    Returns ``None`` when a matching `ClaimSuppressionRule` prunes the
    claim at write time.
    """
    entity_ids_set = set(entity_ids or [])

    # Promoted SVO fields (#984): also accept subject/verb/object via
    # the kwargs above; fall back to metadata['subject'/'verb'/'object']
    # for one release of backwards compat so existing callers keep
    # working before they migrate.
    meta = dict(metadata or {})
    sc = subject_canonical or (meta.get("subject") if isinstance(meta.get("subject"), str) else None)
    sv = predicate_verb or (meta.get("verb") if isinstance(meta.get("verb"), str) else None)
    so = object_phrase or (meta.get("object") if isinstance(meta.get("object"), str) else None)

    # Predicate canonicalisation (#1123 Phase C): every claim that
    # carries a free-text predicate_verb also gets the canonical slug
    # looked up at write time. Unknown verbs → None (honest absence
    # over guessed mapping). Callers don't need to import canonical_verb
    # at every save site; centralising here means new vocabulary
    # additions in kg/_common.py reach every existing writer for free.
    from fichero.kg._common import canonical_verb as _canonical_verb
    pred_canonical = _canonical_verb(sv)

    incoming_svo_subject = svo_subject if svo_subject is not None else sc
    incoming_svo_verb = svo_verb if svo_verb is not None else pred_canonical
    incoming_svo_object = svo_object if svo_object is not None else so

    if source_page_label and source_document_id:
        existing = db.query(
            KnowledgeClaim,
            source_document_id=source_document_id,
            source_page_label=source_page_label,
        )
        for prior in existing:
            if _same_claim_identity(
                prior,
                entity_ids=entity_ids_set,
                text=text,
                svo_subject=incoming_svo_subject,
                svo_verb=incoming_svo_verb or sv,
                svo_object=incoming_svo_object,
            ):
                return prior.id

    suppression_action = _claim_suppression_action(
        db,
        subject_canonical=sc,
        predicate_verb=sv,
        object_phrase=so,
    )
    if suppression_action == ClaimSuppressionRuleAction.prune:
        logger.info(
            "save_claim: pruned claim for subject=%r predicate=%r object=%r",
            sc,
            sv,
            so,
        )
        return None

    claim_confidence = confidence
    claim_curation_state = ClaimCurationState.unreviewed
    if suppression_action == ClaimSuppressionRuleAction.disable:
        claim_curation_state = ClaimCurationState.rejected
    elif suppression_action == ClaimSuppressionRuleAction.demote:
        claim_curation_state = ClaimCurationState.rejected
        claim_confidence = min(confidence, 0.2)

    # Attribution heuristics (#1123 Phase D): derive speaker / audience /
    # quotation_kind from the claim text + excerpt when not explicitly
    # passed. Same centralisation play as predicate_canonical — extractor
    # call sites stay short, new detection rules in this module reach
    # every writer for free. source_language defaults to the existing
    # `language` arg when the caller hasn't separated them (most do not
    # — the distinction matters when a doc has multilingual passages).
    if quotation_kind is None:
        quotation_kind = _detect_quotation_kind(sv, source_excerpt)
    if speaker_name is None:
        speaker_name = _detect_speaker(text, source_excerpt)
    if audience is None:
        audience = _detect_audience(text, source_excerpt)
    if source_language is None:
        source_language = language

    (
        derived_date_values,
        derived_place_values,
        derived_attribution_chain,
        source_support,
    ) = derive_evidential_dimensions(
        db,
        source_document_id=source_document_id,
        source_page_label=source_page_label,
        source_excerpt=source_excerpt,
        source_char_start=source_char_start,
        source_char_end=source_char_end,
        source_bbox=source_bbox,
        confidence=confidence,
        asserted_date_values=date_values,
        asserted_place_values=place_values,
        time_start=time_start,
        time_end=time_end,
        time_precision=time_precision,
        claim_location=claim_location,
        claim_geo=claim_geo,
        attribution_chain=attribution_chain,
        speaker_name=speaker_name,
        provider=provider,
        model=model,
    )
    support_values = _coerce_source_supports(source_supports) or [source_support]
    evidential_confidence_source = (
        "source_anchored"
        if any(value.basis == EvidenceBasis.source_anchored for value in derived_date_values + derived_place_values)
        else confidence_origin
    )

    claim = KnowledgeClaim(
        text=text,
        source_document_id=source_document_id,
        entity_ids=entity_ids or [],
        source_excerpt=source_excerpt,
        source_page_label=source_page_label,
        source_char_start=source_char_start,
        source_char_end=source_char_end,
        source_bbox=source_bbox,
        time_start=time_start,
        time_end=time_end,
        time_precision=time_precision,
        date_values=derived_date_values,
        claim_location=claim_location,
        claim_geo=claim_geo,
        place_values=derived_place_values,
        claim_type=claim_type,
        curation_state=claim_curation_state,
        confidence=claim_confidence,
        metadata=meta,
        epistemic_status=epistemic_status,
        subject_canonical=sc,
        subject_entity_id=subject_entity_id,
        predicate_verb=sv,
        predicate_canonical=pred_canonical,
        object_phrase=so,
        svo_subject=incoming_svo_subject,
        svo_verb=incoming_svo_verb,
        svo_object=incoming_svo_object,
        # Provider attribution (#1113) — which LLM (and any heuristic
        # post-processing) produced this claim. Surface in the inspector
        # so users can audit per-model claim quality.
        provider=provider,
        model=model,
        language=language,
        # #1123 Phase D — attribution fields populated automatically
        # from the claim text + source excerpt unless explicitly passed.
        # provenance_layer defaults to main_text on the model itself.
        source_language=source_language,
        quotation_kind=quotation_kind,
        speaker_name=speaker_name,
        audience=audience,
        confidence_source=confidence_origin,
        attribution_chain=derived_attribution_chain,
        source_supports=support_values,
        corroboration_count=len({support.source_document_id for support in support_values}),
        weighted_corroboration_count=_weighted_corroboration_count(
            db,
            {support.source_document_id for support in support_values},
        ),
        corroborating_source_ids=sorted({support.source_document_id for support in support_values}),
        evidential_confidence=claim_confidence,
        evidential_confidence_source=evidential_confidence_source,
        claim_recorded_at=claim_recorded_at,
    )
    canonical = _find_cross_source_canonical_claim(db, claim)
    if canonical is not None:
        _merge_corroborating_claim(db, canonical, claim)
        return canonical.id
    db.save(claim)
    return claim.id
