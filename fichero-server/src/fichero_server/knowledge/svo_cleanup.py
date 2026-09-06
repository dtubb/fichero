"""Pure, non-destructive cleanup for displayed SVO clauses (#3808)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Protocol

from fichero_server.knowledge.svo_quality import (
    NEAR_DUPLICATE_RATIO,
    claim_rejection,
    same_statement,
    statement_key,
    trim_predicate,
)

NEAR_DUPLICATE_THRESHOLD = 0.86
_DEHYPHENATE = re.compile(r"(?<!\d)([^\W\d_])-\s+([^\W\d_])(?!\d)")
_PERSPECTIVE_VERBS = re.compile(r"\b(?:otorgan|dan|gave|es dado|given)\b", re.I)


class SVOClaim(Protocol):
    id: str
    subject_canonical: str | None
    predicate_verb: str | None
    object_phrase: str | None


@dataclass(frozen=True)
class CleanedClause:
    predicate_verb: str
    object_phrase: str
    source_claim_ids: tuple[str, ...]
    transforms: tuple[str, ...]


def _dehyphenate(text: str) -> str:
    return _DEHYPHENATE.sub(r"\1\2", text)


def _without_repeated_subject(text: str, subject: str) -> str:
    return re.sub(rf"^\s*{re.escape(subject)}\s*[,;:]?\s*", "", text, flags=re.I)


def _comparison_key(verb: str, object_phrase: str) -> str:
    text = _PERSPECTIVE_VERBS.sub("transfer", f"{verb} {object_phrase}").lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def clean_svo_claims(
    claims: Iterable[SVOClaim], *, near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD
) -> list[CleanedClause]:
    """Return display clauses while preserving every absorbed raw claim id."""
    cleaned: list[CleanedClause] = []
    for claim in claims:
        subject = claim.subject_canonical or ""
        verb = _dehyphenate(claim.predicate_verb or "")
        object_phrase = _without_repeated_subject(_dehyphenate(claim.object_phrase or ""), subject)
        transforms = ["dehyphenate"] if verb != (claim.predicate_verb or "") or object_phrase != (claim.object_phrase or "") else []
        key = _comparison_key(verb, object_phrase)
        for index, existing in enumerate(cleaned):
            existing_key = _comparison_key(existing.predicate_verb, existing.object_phrase)
            # One shared standard (svo_quality.same_statement): exact, or same
            # content tokens bar filler/determiners ("signed the deed" vs
            # "signed the said deed"), or the old ratio+token-set rule. A
            # different object head or a different number never collapses.
            if same_statement(key, existing_key, ratio=near_duplicate_threshold):
                cleaned[index] = CleanedClause(existing.predicate_verb, existing.object_phrase, existing.source_claim_ids + (claim.id,), existing.transforms + ("dedup",))
                break
        else:
            cleaned.append(CleanedClause(verb, object_phrase, (claim.id,), tuple(transforms)))
    return cleaned


def clean_extracted_claims(
    subject: str,
    claims: Iterable[dict],
    *,
    source_grounding: bool = False,
    near_duplicate_threshold: float = NEAR_DUPLICATE_RATIO,
) -> list[dict]:
    """Apply the one shared SVO quality standard to model-extracted claim dicts.

    The LLM extraction tools (``extract_svo_only`` / ``extract_all``) build one
    claim per model assertion as a dict carrying at least ``verb`` and
    ``object`` about an entity ``subject``, then persist it verbatim. That path
    never went through ``svo_quality``/``dedupe`` the way the spaCy tier does, so
    run-ons, malformed predicates and near-duplicate repetition reached the
    stored claims untouched (#3808 follow-up). This is the seam that closes that
    gap with the SAME rules both tiers already share.

    Returns a NEW list, order preserved, with:

    * run-on verbs trimmed, overflow moved into the object (``trim_predicate``);
    * malformed / pronoun-subject / self-restating / clause-dump triples
      dropped (``claim_rejection``);
    * near-duplicate statements about this subject collapsed to their first
      occurrence (``statement_key`` + ``same_statement``).

    Dedup uses ``same_statement`` — the standard the display path
    (``clean_svo_claims``) trusts — deliberately, NOT ``near_duplicate``. The
    latter adds a prefix-extension rule ("el cargo" ⊂ "el cargo en 1830") that
    exists to fold the spaCy parser's obj/obl double-emit; the LLM does no such
    double-emit, and a date- or object-extended assertion it makes is a
    genuinely distinct fact that must survive.

    Conservative by construction: distinct numbers, dates and object heads are
    never collapsed (the shared standard guarantees it), and every non-SVO field
    on a surviving claim (``source_text``, ``epistemic_status``, ``claim_type``,
    …) is carried through unchanged.

    ``source_grounding`` is OFF by default. Model verbs/objects are readings of
    the page, not the verbatim spans the spaCy tier emits, so applying
    ``claim_rejection``'s grounding rule to them would reject faithful claims
    whose surface form differs from the cited excerpt. The structural rejections
    (pronoun subject, empty/non-word predicate, subject-restating or clause-dump
    object) always apply.
    """
    kept: list[dict] = []
    kept_predicates: list[str] = []
    for claim in claims:
        verb, obj = trim_predicate(claim.get("verb", ""), claim.get("object", ""))
        source_text = claim.get("source_text") if source_grounding else None
        if claim_rejection(subject, verb, obj, source_text) is not None:
            continue
        # statement_key drops a leading copy of the subject inside the object, so
        # "otorgó Andrés poder" and "otorgó poder" compare equal.
        _subject_key, predicate = statement_key(subject, verb, obj)
        if any(
            same_statement(predicate, seen, ratio=near_duplicate_threshold)
            for seen in kept_predicates
        ):
            continue
        cleaned = dict(claim)
        cleaned["verb"] = verb
        cleaned["object"] = obj
        kept.append(cleaned)
        kept_predicates.append(predicate)
    return kept
