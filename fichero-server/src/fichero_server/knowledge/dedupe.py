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
from fichero_server.knowledge.svo_quality import same_statement
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
#: The same name written differently (`kg.entity.variant-spellings-proposed`): proposed for review, never merged.
BASIS_SPELLING = "spelling-variant"


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


# --- The same name written differently (kg.entity.variant-spellings-proposed) ------------------------------------
# Usual abbreviations of names in Spanish colonial and notarial hands, keyed by the token with its points and raised
# letters dropped (`Fran.co` -> `franco`, `Pº` -> `po`). ponytail: fixed lists; a project's own list belongs in its
# recipe's name-normalisation step when one exists.
#: Read as an abbreviation only when written as one, with a point or a raised letter: plain, each is a word or a
#: name of its own (the surname `Franco`, `Ana`, `Alo`).
_MARKED_ABBREVIATIONS = {
    "fran": "francisco", "franco": "francisco", "ant": "antonio", "anto": "antonio", "po": "pedro",
    "dio": "diego", "gonzo": "gonzalo", "alo": "alonso", "ju": "juan", "mel": "manuel", "sta": "santa",
    "sto": "santo", "sn": "san",
}
#: Contractions that are no word, read as abbreviations however written.
_CONTRACTIONS = {
    "fco": "francisco", "frco": "francisco", "dgo": "domingo", "xpoval": "cristobal", "xptoval": "cristobal",
    "xpobal": "cristobal", "xpl": "cristobal", "jn": "juan", "bme": "bartolome", "bartme": "bartolome",
    "manl": "manuel", "migl": "miguel", "jph": "joseph", "fernz": "fernandez", "frz": "fernandez",
    "glz": "gonzalez", "gonz": "gonzalez", "gzlez": "gonzalez", "rodz": "rodriguez", "rodrz": "rodriguez",
    "mrz": "martinez", "mtz": "martinez", "hdz": "hernandez", "hernz": "hernandez", "lopz": "lopez",
}
#: Spellings of one name (not abbreviations), read so however written.
_SAME_NAME = {"josef": "joseph", "jose": "joseph"}
#: Titles and offices set aside: `Don Juan de Mosquera` is the name `Juan de Mosquera`.
_TITLES = frozenset({
    "don", "dn", "d", "dona", "da", "senor", "sr", "sra", "senora", "capitan", "cap", "capn", "fray", "fr",
    "padre", "licenciado", "lic", "ldo", "doctor", "dr", "alferez", "maestre", "mro", "presbitero", "pbro",
})


def _old_spelling(token: str) -> str:
    """One spelling for the sounds early-modern Spanish wrote several ways. Letters only; digits are kept."""
    t = token.replace("ph", "f").replace("th", "t").replace("ch", "\x01")
    t = re.sub(r"qu|q", "k", t)
    t = re.sub(r"c(?=[ei])", "s", t)
    t = re.sub(r"g(?=[ei])", "j", t)
    t = t.replace("c", "k").replace("z", "s").replace("x", "j").replace("y", "i").replace("v", "b")
    t = t.replace("h", "").replace("\x01", "ch")
    t = re.sub(r"n(?=[bp])", "m", t)
    return re.sub(r"(\D)\1+", r"\1", t)


def spelling_key(name: str) -> str:
    """The key two spellings of one name share: case, accents, punctuation, old spelling, the usual abbreviations
    and titles set aside; numbers and every other letter kept (`Dredge No. 1` is not `Dredge No. 3`)."""
    keys = []
    # An abbreviation's points and raised letters join its pieces (`fran.co` -> `franco`) and mark it as one.
    for raw in re.split(r"[^\w.:'’ºª]+", name.casefold().replace("ç", "z")):
        marked = bool(re.search(r"[.:ºª]", raw))
        token = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
        token = re.sub(r"[^\w]", "", token)
        if not token or token in _TITLES:
            continue
        token = _CONTRACTIONS.get(token) or _SAME_NAME.get(token) or (
            _MARKED_ABBREVIATIONS.get(token, token) if marked else token)
        keys.append(_old_spelling(token))
    return " ".join(keys)


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
        weakness = {BASIS_NORMALIZED_NAME: 0, BASIS_ALIAS_COLLISION: 1, BASIS_SPELLING: 2, BASIS_SIMILARITY: 3}
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
    spelling_variants: bool = False,
) -> list[EntityMergeGroup]:
    """Plan same-type entity merges by normalized name / alias collision.

    ``min_similarity`` additionally unions same-type pairs whose normalized
    canonical names reach that ``SequenceMatcher`` ratio (opt-in tier).
    ``spelling_variants`` additionally unions same-type names sharing a
    ``spelling_key`` (opt-in; its groups are proposals for review, never applied).
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

    if spelling_variants:
        owner: dict[tuple[str, str], int] = {}
        for i, entity in enumerate(live):
            key = (spelling_key(entity.canonical_name), entity.entity_type.value)
            if not key[0]:
                continue
            if key in owner:
                if uf.find(owner[key]) != uf.find(i):
                    a, b = normalize_name(live[owner[key]].canonical_name), normalize_name(entity.canonical_name)
                    uf.union(owner[key], i, BASIS_SPELLING, SequenceMatcher(None, a, b).ratio())
            else:
                owner[key] = i

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
    groups.sort(key=lambda g: (g.basis in (BASIS_SPELLING, BASIS_SIMILARITY), g.survivor.canonical_name))
    return groups


def _direct_basis(a: KnowledgeEntity, b: KnowledgeEntity) -> str | None:
    """Why two entities' own names match, or None."""
    if normalize_name(a.canonical_name) == normalize_name(b.canonical_name):
        return BASIS_NORMALIZED_NAME
    names_a = {normalize_name(n) for n in [a.canonical_name, *a.aliases]} - {""}
    names_b = {normalize_name(n) for n in [b.canonical_name, *b.aliases]} - {""}
    if names_a & names_b:
        return BASIS_ALIAS_COLLISION
    if spelling_key(a.canonical_name) and spelling_key(a.canonical_name) == spelling_key(b.canonical_name):
        return BASIS_SPELLING
    return None


def direct_pairs(group: EntityMergeGroup) -> list[tuple[KnowledgeEntity, KnowledgeEntity, str, float]]:
    """The pairs to propose for a group (`kg.entity.variant-spellings-proposed`): each member against the
    best-ranked member its OWN names match, never one it is joined to only through a third (proposing every
    member against the survivor chained strangers together through a stray alias). One pair per member, so a
    name written three ways is two pairs, not three: (the one more likely to stay, the other, basis, similarity)."""
    members = sorted([group.survivor, *group.absorbed], key=_entity_survivor_rank, reverse=True)
    out = []
    for rank, member in enumerate(members):
        for better in members[:rank]:
            basis = _direct_basis(better, member)
            if basis:
                ratio = SequenceMatcher(None, normalize_name(better.canonical_name), normalize_name(member.canonical_name))
                out.append((better, member, basis, round(ratio.ratio(), 4)))
                break
    return out


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
    near-duplicate tier (opt-in) collapses statements the shared
    ``svo_quality.same_statement`` standard judges equal — word-order and
    inflection variants, and filler/determiner insertions ("the deed" vs "the
    said deed") — while a different object head or a different date/number never
    collapses.
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
                    if same_statement(keys[a], keys[b], ratio=near_duplicate_threshold):
                        ratio = SequenceMatcher(None, keys[a], keys[b]).ratio()
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
