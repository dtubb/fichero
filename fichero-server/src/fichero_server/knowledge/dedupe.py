"""Batch dedupe PLANNING for KG entities and SVO claims (#4508).

Pure functions: they read model rows and return a merge *plan*; nothing here
writes. The apply step lives with the routes, which drive every merge through
the audited ``entity.merge`` / ``claim.merge`` actions (EPIC #1848) so each
merge gets an ActionAudit row, an EntityMergeAudit/ClaimMergeAudit, an
observable-layer emit, and undo — the same machinery a hand merge uses.

Quality gates, structural not checked:
- Grouping keys INCLUDE ``entity_type`` — a cross-type merge cannot be planned.
- Absorbed members are ``unreviewed`` only, unless the caller opts in;
  ``rejected`` and already-merged rows never participate.
- The similarity tier is opt-in (``min_similarity``); by default only exact
  normalized-name / alias collisions are planned. On the Marshall survey the
  exact tier was all true duplicates while 0.90-similarity pairs included
  "Dredge No. 3" vs "Dredge No. 1" — similar is a review queue, not a merge.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Sequence

from fichero_server.knowledge.svo_cleanup import _comparison_key
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityCurationState,
    KnowledgeClaim,
    KnowledgeEntity,
)

# Exact tier bases, in display order.
BASIS_NORMALIZED_NAME = "normalized-name"
BASIS_ALIAS_COLLISION = "alias-collision"
BASIS_SIMILARITY = "similarity"


def normalize_name(name: str) -> str:
    """Accent-, case-, punctuation- and whitespace-insensitive name key.

    Collapses the noise forms the Marshall survey actually found:
    ``Quibdó``/``Quibdo``, ``Jorge\\nCardenas``/``Jorge Cardenas``,
    ``B'na``/``B/na``, ``"La Piedra"``/``La Piedra``, ``Laura C. Hall``/
    ``Laura C Hall``.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", stripped.casefold()).split())


@dataclass
class EntityMergeGroup:
    survivor: KnowledgeEntity
    absorbed: list[KnowledgeEntity]
    basis: str
    similarity: float | None = None


@dataclass
class ClaimMergeGroup:
    survivor: KnowledgeClaim
    absorbed: list[KnowledgeClaim]
    basis: str
    similarity: float | None = None


@dataclass
class _Union:
    """Tiny union-find over row indices, tracking the best basis per edge."""

    parent: list[int]
    basis: dict[int, str] = field(default_factory=dict)
    similarity: dict[int, float] = field(default_factory=dict)

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int, basis: str, similarity: float | None = None) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        self.parent[rb] = ra
        # A group's displayed basis is its weakest edge — similarity taints.
        weakness = {BASIS_NORMALIZED_NAME: 0, BASIS_ALIAS_COLLISION: 1, BASIS_SIMILARITY: 2}
        candidates = [basis, *(self.basis[r] for r in (ra, rb) if r in self.basis)]
        self.basis[ra] = max(candidates, key=lambda b_: weakness[b_])
        scores = [similarity, self.similarity.get(ra), self.similarity.get(rb)]
        known = [s for s in scores if s is not None]
        if known:
            self.similarity[ra] = min(known)


def _name_noise(name: str) -> int:
    """Punctuation/linebreak characters — the messier duplicate loses ties."""
    return sum(1 for c in name if not (c.isalnum() or c == " "))


def _entity_survivor_rank(entity: KnowledgeEntity) -> tuple:
    """Higher tuple wins. Curated work outranks machine output (#4415 spirit)."""
    return (
        entity.curation_state != EntityCurationState.unreviewed,
        entity.corroboration_count,
        -_name_noise(entity.canonical_name),
        len(entity.aliases),
        -entity.created_at.timestamp(),
    )


def plan_entity_dedupe(
    entities: Iterable[KnowledgeEntity],
    *,
    include_reviewed: bool = False,
    min_similarity: float | None = None,
) -> list[EntityMergeGroup]:
    """Plan same-type entity merges by normalized name / alias collision.

    ``min_similarity`` additionally unions same-type pairs whose normalized
    canonical names reach that ``SequenceMatcher`` ratio (opt-in tier).
    """
    live = [
        e
        for e in entities
        if e.merged_into_id is None and e.curation_state != EntityCurationState.rejected
    ]
    uf = _Union(parent=list(range(len(live))))

    name_key_owner: dict[tuple[str, str], int] = {}
    alias_key_owner: dict[tuple[str, str], int] = {}
    for i, entity in enumerate(live):
        etype = entity.entity_type.value
        name_key = (normalize_name(entity.canonical_name), etype)
        if name_key[0]:
            if name_key in name_key_owner:
                uf.union(name_key_owner[name_key], i, BASIS_NORMALIZED_NAME)
            else:
                name_key_owner[name_key] = i
        for alias in entity.aliases:
            key = (normalize_name(alias), etype)
            if not key[0] or key == name_key:
                continue
            # An alias colliding with another entity's canonical name or alias.
            if key in name_key_owner and name_key_owner[key] != i:
                uf.union(name_key_owner[key], i, BASIS_ALIAS_COLLISION)
            if key in alias_key_owner and alias_key_owner[key] != i:
                uf.union(alias_key_owner[key], i, BASIS_ALIAS_COLLISION)
            alias_key_owner.setdefault(key, i)
        # A canonical name colliding with an earlier entity's alias.
        if name_key in alias_key_owner and alias_key_owner[name_key] != i:
            uf.union(alias_key_owner[name_key], i, BASIS_ALIAS_COLLISION)

    if min_similarity is not None:
        by_type: dict[str, list[int]] = {}
        for i, entity in enumerate(live):
            by_type.setdefault(entity.entity_type.value, []).append(i)
        for indices in by_type.values():
            keys = {i: normalize_name(live[i].canonical_name) for i in indices}
            for pos, a in enumerate(indices):
                for b in indices[pos + 1 :]:
                    if not keys[a] or not keys[b] or uf.find(a) == uf.find(b):
                        continue
                    ratio = SequenceMatcher(None, keys[a], keys[b]).ratio()
                    if ratio >= min_similarity:
                        uf.union(a, b, BASIS_SIMILARITY, ratio)

    return _entity_groups(live, uf, include_reviewed=include_reviewed)


def _entity_groups(
    live: Sequence[KnowledgeEntity], uf: _Union, *, include_reviewed: bool
) -> list[EntityMergeGroup]:
    clusters: dict[int, list[int]] = {}
    for i in range(len(live)):
        clusters.setdefault(uf.find(i), []).append(i)

    groups: list[EntityMergeGroup] = []
    for root, indices in clusters.items():
        if len(indices) < 2:
            continue
        members = [live[i] for i in indices]
        survivor = max(members, key=_entity_survivor_rank)
        absorbed = [
            m
            for m in members
            if m.id != survivor.id
            and (include_reviewed or m.curation_state == EntityCurationState.unreviewed)
        ]
        if not absorbed:
            continue
        groups.append(
            EntityMergeGroup(
                survivor=survivor,
                absorbed=sorted(absorbed, key=lambda e: e.id),
                basis=uf.basis.get(root, BASIS_NORMALIZED_NAME),
                similarity=uf.similarity.get(root),
            )
        )
    groups.sort(key=lambda g: (g.basis == BASIS_SIMILARITY, g.survivor.canonical_name))
    return groups


def _claim_statement_key(claim: KnowledgeClaim) -> str:
    """One comparable statement key per claim: SVO when present, else text."""
    if claim.predicate_verb or claim.object_phrase:
        return _comparison_key(claim.predicate_verb or "", claim.object_phrase or "")
    return normalize_name(claim.text)


def _claim_subject_key(claim: KnowledgeClaim) -> str:
    return claim.subject_entity_id or normalize_name(claim.subject_canonical or "")


def _claim_survivor_rank(claim: KnowledgeClaim) -> tuple:
    return (
        claim.curation_state != ClaimCurationState.unreviewed,
        claim.corroboration_count,
        len(claim.source_supports),
        -claim.created_at.timestamp(),
    )


def plan_claim_dedupe(
    claims: Iterable[KnowledgeClaim],
    *,
    include_reviewed: bool = False,
    near_duplicate_threshold: float | None = None,
) -> list[ClaimMergeGroup]:
    """Plan merges of duplicate statements about the SAME subject.

    Exact tier: identical ``(subject, normalized verb+object)`` — the same
    normalization the display path (`svo_cleanup`) already trusts. The
    near-duplicate tier (opt-in) additionally requires the identical token set,
    mirroring ``clean_svo_claims``, so word-order/punctuation variants collapse
    but genuinely different statements never do.
    """
    live = [
        c
        for c in claims
        if c.merged_into_id is None and c.curation_state != ClaimCurationState.rejected
    ]
    uf = _Union(parent=list(range(len(live))))

    exact_owner: dict[tuple[str, str], int] = {}
    subjects: dict[str, list[int]] = {}
    for i, claim in enumerate(live):
        subject = _claim_subject_key(claim)
        if not subject:
            continue  # a claim with no subject has no safe dedupe identity
        statement = _claim_statement_key(claim)
        if not statement:
            continue
        subjects.setdefault(subject, []).append(i)
        key = (subject, statement)
        if key in exact_owner:
            uf.union(exact_owner[key], i, BASIS_NORMALIZED_NAME)
        else:
            exact_owner[key] = i

    if near_duplicate_threshold is not None:
        for indices in subjects.values():
            keys = {i: _claim_statement_key(live[i]) for i in indices}
            for pos, a in enumerate(indices):
                for b in indices[pos + 1 :]:
                    if uf.find(a) == uf.find(b):
                        continue
                    if set(keys[a].split()) != set(keys[b].split()):
                        continue
                    ratio = SequenceMatcher(None, keys[a], keys[b]).ratio()
                    if ratio >= near_duplicate_threshold:
                        uf.union(a, b, BASIS_SIMILARITY, ratio)

    clusters: dict[int, list[int]] = {}
    for i in range(len(live)):
        clusters.setdefault(uf.find(i), []).append(i)

    groups: list[ClaimMergeGroup] = []
    for root, indices in clusters.items():
        if len(indices) < 2:
            continue
        members = [live[i] for i in indices]
        survivor = max(members, key=_claim_survivor_rank)
        absorbed = [
            m
            for m in members
            if m.id != survivor.id
            and (include_reviewed or m.curation_state == ClaimCurationState.unreviewed)
        ]
        if not absorbed:
            continue
        groups.append(
            ClaimMergeGroup(
                survivor=survivor,
                absorbed=sorted(absorbed, key=lambda c: c.id),
                basis=uf.basis.get(root, BASIS_NORMALIZED_NAME),
                similarity=uf.similarity.get(root),
            )
        )
    groups.sort(key=lambda g: (g.basis == BASIS_SIMILARITY, g.survivor.text))
    return groups
