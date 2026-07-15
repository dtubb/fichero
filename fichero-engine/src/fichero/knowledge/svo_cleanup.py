"""Pure, non-destructive cleanup for displayed SVO clauses (#3808)."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable, Protocol

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
            if key == existing_key or (
                SequenceMatcher(None, key, existing_key).ratio() >= near_duplicate_threshold
                and set(key.split()) == set(existing_key.split())
            ):
                cleaned[index] = CleanedClause(existing.predicate_verb, existing.object_phrase, existing.source_claim_ids + (claim.id,), existing.transforms + ("dedup",))
                break
        else:
            cleaned.append(CleanedClause(verb, object_phrase, (claim.id,), tuple(transforms)))
    return cleaned
