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
from typing import Optional

from fichero.db import Database
from fichero.knowledge_models import (
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
    QuotationKind,
)

logger = logging.getLogger(__name__)


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

    # Normalise: lower, drop punctuation. Token-set similarity is
    # more forgiving of reordering than raw SequenceMatcher.ratio.
    def _tokens(s: str) -> set[str]:
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())
        return {tok for tok in cleaned.split() if len(tok) > 2}

    needle_tokens = _tokens(canonical_name)
    needle_lower = canonical_name.lower()

    best: tuple[float, Optional[KnowledgeEntity]] = (0.0, None)
    for ent in existing:
        # Two metrics, take the max so either signal can hit threshold.
        seq_ratio = SequenceMatcher(None, needle_lower, ent.canonical_name.lower()).ratio()
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


def upsert_entity(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> str:
    """Look up entity by ``(canonical_name, entity_type)``; create if missing.

    Three-stage match (#897 → #899 Phase B):
    1. Exact ``(canonical_name, entity_type)`` lookup — covers stable
       names like "Eugenio Córdoba" repeated across pages.
    2. **Embedding cosine** via LanceDB (`kg.entity_vectors`) over
       same-type entities. Catches semantic divergence in noun
       phrases ("Racial Economic Exclusion" vs "Race and Economic
       Marginalization") that pure SequenceMatcher misses. Cosine
       >= 0.92 → auto-merge; 0.75–0.92 → logged for future review
       gate (#377); <0.75 → fall through.
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
    existing = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if existing:
        return existing[0].id

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
            if best_score >= entity_vectors.AUTO_MERGE_THRESHOLD:
                matched = db.get(KnowledgeEntity, best_id)
                if matched is not None:
                    logger.info(
                        "upsert_entity: embedding auto-merge %r → %s (%r, cosine=%.3f)",
                        canonical_name, best_id, best_name, best_score,
                    )
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
        except Exception:
            pass
        return matched.id

    # Stage 4: create a brand-new entity + index its vector.
    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
    )
    db.save(entity)
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
) -> str:
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
    """
    from difflib import SequenceMatcher

    entity_ids_set = set(entity_ids or [])
    if source_page_label and source_document_id:
        existing = db.query(
            KnowledgeClaim,
            source_document_id=source_document_id,
            source_page_label=source_page_label,
        )
        for prior in existing:
            if set(prior.entity_ids) != entity_ids_set:
                continue
            ratio = SequenceMatcher(None, prior.text, text).ratio()
            if ratio >= 0.9:
                return prior.id

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
        claim_type=claim_type,
        confidence=confidence,
        metadata=meta,
        epistemic_status=epistemic_status,
        subject_canonical=sc,
        subject_entity_id=subject_entity_id,
        predicate_verb=sv,
        predicate_canonical=pred_canonical,
        object_phrase=so,
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
    )
    db.save(claim)
    return claim.id
