"""Pure, non-destructive cleanup for displayed SVO clauses (#3808)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Protocol

from fichero_server.knowledge.svo_quality import (
    NEAR_DUPLICATE_RATIO,
    same_statement,
    statement_key,
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


def collapse_near_duplicate_claims(
    subject: str,
    claims: Iterable[dict],
    *,
    near_duplicate_threshold: float = NEAR_DUPLICATE_RATIO,
) -> list[dict]:
    """Collapse near-duplicate model-extracted claim dicts about one subject.

    The LLM extraction path (``_extract_claims_for_entity``) already trims each
    claim (``trim_predicate``) and rejects the malformed/ungrounded ones
    (``claim_rejection`` + ``predicate_problem``). What it never did was collapse
    two SURVIVING claims that say the same thing — a model re-asserting "otorgó
    poder" as "otorgó el poder", or repeating a claim across chunks, left both
    rows standing. That is the repetition Daniel saw on the Istmina run.

    Each claim is a dict carrying ``verb`` and ``object`` about an entity
    ``subject``. Returns the surviving claims in order, first occurrence kept,
    every field carried through untouched (nothing is mutated).

    Uses ``same_statement`` — the standard the display path (``clean_svo_claims``)
    trusts — deliberately, NOT ``near_duplicate``. The latter adds a
    prefix-extension rule ("el cargo" ⊂ "el cargo en 1830") that exists to fold
    the spaCy parser's obj/obl double-emit; the LLM does no such double-emit, and
    a date- or object-extended assertion it makes is a distinct fact that must
    survive. Distinct numbers, dates and object heads are never collapsed.
    """
    kept: list[dict] = []
    kept_predicates: list[str] = []
    for claim in claims:
        # statement_key folds surface noise and drops a leading copy of the
        # subject inside the object, so "otorgó Andrés poder" and "otorgó poder"
        # compare equal.
        _subject_key, predicate = statement_key(
            subject, claim.get("verb", ""), claim.get("object", "")
        )
        if any(
            same_statement(predicate, seen, ratio=near_duplicate_threshold)
            for seen in kept_predicates
        ):
            continue
        kept.append(claim)
        kept_predicates.append(predicate)
    return kept
