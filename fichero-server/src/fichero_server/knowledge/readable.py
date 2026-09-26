"""Deterministic readable rendering of the KG (biography / regest / gazetteer).

spec: docs/contributor_manual/specs/kg-readable-representation.md

The Reiter & Dale NLG pipeline, built as small pure functions over KnowledgeClaim so the
whole thing is testable without a GUI, an engine, or an LLM. NOTHING here calls a model:
the prose is a pure function of stored claims (the `narrative_v1` LLM prompt is what this
replaces). Sentence-level composition already lives in `knowledge/paragraph.py`; this module
adds the entry/biography-scale stages around it (Reiter & Dale). Built so far:

  1. content determination — `select_entry_claims`: which claims belong in an entry.
  2. document structuring   — `order_claims`: chronological (time_start / date_values)
     or by source (document → page → offset).
  3. aggregation            — `aggregate_claims`: collapse claims sharing a subject
     IDENTITY, verb, AND language into distinct objects + place distribution, keeping
     every claim_id for citation. Wired into `render_entry` (#4839/#4649).
  5. referring expressions  — `referring_expression`: full name first, family name after.
  6. realisation            — `render_aggregation` / `_render_group_sentence`: phrase an
     Aggregation per language (the verb + objects stay the claim's own words; only the
     conjunction between objects and the place glue are language-table lookups).

Not yet built: stage 4 (lexicalisation — per-language verb lexicon) beyond the count/place
glue; deferred until the corpus's languages + real verb vocab are grounded (spec open Q).
See docs/contributor_manual/specs/kg-readable-representation.md for the pipeline + behaviors.
"""
from __future__ import annotations

import re
import unicodedata

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from fichero_server.knowledge._common import order_statement_parts
from fichero_server.knowledge.paragraph import (
    _claim_object,
    _claim_sentence,
    _claim_subject,
    _claim_verb,
    _normalize,
    _sentence_end,
)
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


class Ordering(str, Enum):
    """How an entry's claims are sequenced (Reiter & Dale stage 2)."""

    chronological = "chronological"
    by_source = "by_source"


def select_entry_claims(
    claims: Sequence[KnowledgeClaim], entity_id: str
) -> list[KnowledgeClaim]:
    """Stage 1 — content determination.

    The claims that belong in ``entity_id``'s entry: those it is the subject of, plus those
    that mention it (``entity_ids``). Input order is preserved (structuring is stage 2's job).
    """
    return [
        claim
        for claim in claims
        if claim.subject_entity_id == entity_id or entity_id in (claim.entity_ids or [])
    ]


def _chronological_key(claim: KnowledgeClaim) -> tuple[bool, str]:
    # Undated claims sort last (True > False); dated claims sort by their start.
    # time_start is an ISO-ish string, so a lexical sort is date order. Ties keep
    # input order because Python's sort is stable. The spec dates a claim by its
    # event/attestation date, so when time_start is absent fall back to the
    # earliest `date_values` start (evidential dates) before treating it as undated.
    start = claim.time_start
    if not start and claim.date_values:
        starts = [dv.start for dv in claim.date_values if dv.start]
        if starts:
            start = min(starts)
    start = start or ""
    return (start == "", start)


def _by_source_key(claim: KnowledgeClaim) -> tuple[bool, str, str, int]:
    # Group by source document, then by position within it (page, then char offset),
    # so a reader can follow one record at a time. Sourceless (manually-asserted)
    # claims sort last.
    doc = claim.source_document_id or ""
    return (
        doc == "",
        doc,
        claim.source_page_label or "",
        claim.source_char_start if claim.source_char_start is not None else 0,
    )


def order_claims(
    claims: Sequence[KnowledgeClaim], ordering: Ordering
) -> list[KnowledgeClaim]:
    """Stage 2 — document structuring. Deterministic; never drops a claim."""
    if ordering == Ordering.chronological:
        return sorted(claims, key=_chronological_key)
    return sorted(claims, key=_by_source_key)


@dataclass
class Aggregation:
    """Stage 3 output — one (subject, verb, language) collapsed across its claims.

    Repetition becomes a count plus the distinct objects/places, so "witnessed the
    will, witnessed the sale, …" renders as one sentence. `claim_ids` keeps every
    contributing claim for citation (provenance is never lost by aggregating).
    `language` and `subject_entity_id` are the group's shared values (every member
    was grouped BECAUSE they match) — kept on the dataclass so a caller never has
    to re-derive what already gated the merge.
    """

    subject: str | None
    verb: str | None
    objects: list[str]
    places: list[str]
    count: int
    claim_ids: list[str]
    language: str | None = None
    subject_entity_id: str | None = None


def _claim_language(claim: KnowledgeClaim) -> str | None:
    return claim.source_languages[0] if claim.source_languages else None


def _fold(text: str) -> str:
    """Case- and accent-fold, the same normalization `svo_quality.py`/
    `spacy_svo.py` already use for closed-list matching in this codebase."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


# Leading prepositions, by language, that mark an object slot's role as
# non-neutral: a recipient ("to Pedro Mosquera" / "a Pedro Mosquera") or a
# place/instrument, never a plain patient. Beside the conjunction table
# (`_REALISATION`) for the same reason: both are the small, closed,
# per-language tables this module's realisation stage is built from.
_LEADING_PREPOSITIONS = {
    "en": {
        "to", "from", "in", "at", "on", "by", "with", "for", "of", "into",
        "before", "after",
    },
    "es": {
        "a", "al", "de", "del", "en", "por", "para", "con", "ante", "desde",
        "hasta", "sobre",
    },
}


def _is_prepositional_object(obj: str | None, language: str | None) -> bool:
    """True when `obj`'s first word is a leading preposition in ITS OWN
    declared language (#4836).

    An object slot carries no ROLE today (`kg.read.object-slot-has-no-role`
    is an open, named GAP) -- a claim's object could be the recipient or the
    patient, distinguished today only by whichever preposition survived in
    the extracted text. Coordinating a prepositional object with a plain one
    under a conjunction reads as if both were the same kind of thing.
    Spanish makes this the gravest case: "a" marks a PERSON direct object, so
    "vendió la mina y a Pedro Mosquera" ("sold the mine and Pedro Mosquera")
    reads as Pedro being sold alongside the mine -- exactly the false
    sentence #4836 removed from EXTRACTION itself (7c6f1aae5); aggregation
    must not bring it back by a different route.

    Deliberately checks ONLY the claim's own language's table, never every
    table at once: Spanish "a" and the English indefinite article "a" are
    the same folded string, so checking both tables for an unlabelled claim
    would flag ordinary English objects ("a will", "a mine") as
    prepositional by accident. A claim with no declared language is not
    classified as prepositional by this check -- it can still be forced
    solo by ruling A (no resolved subject entity) or simply never collide
    with anything sharing its (subject, verb, language) key.
    """
    if not obj or not language:
        return False
    table = _LEADING_PREPOSITIONS.get(language)
    if table is None:
        return False
    first_word = obj.strip().split(" ", 1)[0]
    if not first_word:
        return False
    return _fold(first_word) in table


def _is_solo_claim(claim: KnowledgeClaim) -> bool:
    """True when `claim` must never merge with any other claim.

    Three independent rulings (#4836), all "narrower and always true beats
    smoother and sometimes false": (A) a claim with no RESOLVED subject
    entity never merges -- text-only identity risks attributing one
    person's act to a namesake (a father and son sharing a written name);
    (B) a claim whose object is a prepositional phrase never merges with
    ANYTHING, including another prepositional-object claim -- see
    `_is_prepositional_object`.
    """
    if not claim.subject_entity_id:
        return True
    # (C) a claim that declares NO language never merges. Without a language
    # the prepositional check below cannot run (it reads only the claim's own
    # language's table, because Spanish "a" and the English article "a" fold
    # alike), so a recipient would merge after all, and the conjunction would
    # fall back to English glue inside a sentence in another language:
    # "vendió la mina and a Pedro Mosquera".
    # The same holds for a DECLARED language with no glue table ("fr"): it
    # would merge and take English "and" inside a French sentence. A language
    # this module cannot join in, it does not join. One test covers both.
    if _claim_language(claim) not in _REALISATION:
        return True
    if _is_prepositional_object(_claim_object(claim), _claim_language(claim)):
        return True
    return False


def _subject_identity_key(claim: KnowledgeClaim) -> str:
    """A merge-safe identity for the claim's subject (#4839, #4836).

    A resolved subject entity id IS the identity -- namespaced ("id:") so
    it can never collide with anything else. A claim `_is_solo_claim` marks
    gets a key unique to ITSELF (its own id), which guarantees it groups
    alone: no other claim can ever share a randomly-generated claim id.
    """
    if _is_solo_claim(claim):
        return f"solo:{claim.id}"
    return f"id:{claim.subject_entity_id}"


def aggregate_claims(claims: Sequence[KnowledgeClaim]) -> list[Aggregation]:
    """Stage 3 — aggregation. Group claims by (subject IDENTITY, verb, language);
    within a group keep the count of claims and the DISTINCT objects. First-seen
    group order is preserved (ordering is stage 2's job; this doesn't re-sort). No
    claim is dropped — every id is retained for citation.

    Fixes folded in here, all against real corpus shapes, not just unwired
    (#4839, #4649, #4836): the key is subject-IDENTITY-aware, not text-only
    (see `_subject_identity_key`), so a same-named different entity never
    merges; the key includes the claim's own language, so a Spanish and an
    English claim that happen to normalize to the same subject/verb text
    never merge into one sentence with one glue language; a claim with no
    RESOLVED subject entity never merges with anything (`_is_solo_claim`
    ruling A — text-only identity is not safe enough to found a merge on);
    and a claim whose object is a prepositional phrase never merges with
    anything either (ruling B — `_is_prepositional_object`), because the
    real extraction shape stores a recipient as its own claim
    ("sold" / "to Pedro Mosquera") and coordinating that under "y"/"and"
    beside a plain patient reads as if they were the same kind of thing —
    in Spanish specifically, marking a PERSON as a coordinated direct
    object is the exact false sentence #4836 removed from extraction.
    """
    groups: dict[tuple[str, str, str | None], Aggregation] = {}
    order: list[tuple[str, str, str | None]] = []
    for claim in claims:
        subject = _claim_subject(claim)
        verb = _claim_verb(claim)
        obj = _claim_object(claim)
        language = _claim_language(claim)
        key = (_subject_identity_key(claim), _normalize(verb or ""), language)
        agg = groups.get(key)
        if agg is None:
            agg = Aggregation(
                subject=subject,
                verb=verb,
                objects=[],
                places=[],
                count=0,
                claim_ids=[],
                language=language,
                subject_entity_id=claim.subject_entity_id,
            )
            groups[key] = agg
            order.append(key)
        agg.count += 1
        agg.claim_ids.append(claim.id)
        if obj is not None and obj not in agg.objects:
            agg.objects.append(obj)
        place = claim.claim_location
        if place and place not in agg.places:
            agg.places.append(place)
    return [groups[key] for key in order]


def referring_expression(full_name: str, *, first_mention: bool) -> str:
    """Stage 5 — referring expressions.

    Full name on first mention; the family name thereafter. ponytail: "family name =
    last whitespace token" is a heuristic that holds for most Spanish/European names
    in the corpus (e.g. "María de Córdoba" -> "Córdoba"); refine per-language (two
    Spanish surnames, particles like "de la") if it proves too blunt. Pronoun-level
    reference (stage 5's finer grain) needs the entity's gender + language and lands
    with lexicalisation.
    """
    name = " ".join(full_name.split())  # collapse whitespace
    if not name:
        return ""
    if first_mention:
        return name
    tokens = name.split(" ")
    return tokens[-1] if len(tokens) > 1 else name


# Stage 6 — realisation. ponytail: a minimal per-language phrase table for the
# count/place scaffolding ONLY. The verb + objects come from the claim's own SVO
# (already in the source's language — we never translate); this table supplies the
# language-specific glue ("N veces", "en X y Y" / "N times", "at X and Y"). Add a
# language by adding a row. Escalate to Grammatical Framework (the Abstract
# Wikipedia path) only when morphology outgrows this.
_REALISATION = {
    "es": {"times": "veces", "at": "en", "and": "y"},
    "en": {"times": "times", "at": "at", "and": "and"},
}


def _join_list(items: list[str], conjunction: str) -> str:
    """"A, B y C" / "A, B and C" — the last item joined by the language's conjunction."""
    parts = [p for p in items if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} {conjunction} {parts[-1]}"


def _without_repeated_preposition(verb: str | None, obj: str, language: str | None) -> str:
    """"arrived at" + "at Andagoya" reads "arrived at at Andagoya" (#5008): extraction left the
    preposition on BOTH sides. When the verb's last word and the object's first word are the same
    preposition in this language's own table, say it once. Only ever drops the object's copy of a
    word that is a preposition, never any other text (an English "a" is not in `en`'s table)."""
    if not verb or not obj:
        return obj
    table = _LEADING_PREPOSITIONS.get(language or "", set())
    last = _fold(verb.split()[-1]) if verb.split() else ""
    first, _, rest = obj.strip().partition(" ")
    if rest and last in table and _fold(first) == last:
        return rest.strip()
    return obj


def render_aggregation(agg: "Aggregation", language: str) -> str:
    """Stage 6 — realise one Aggregation into a sentence in `language`.

    `language` is REQUIRED. It defaulted to "es" until 2026-09-26, which meant a
    caller who simply forgot it got Spanish glue around English words and no
    error — the exact silent-wrong-default that `kg.read.source-language-only`
    forbids. Nothing in the engine called it without a language (every caller
    passes `agg.language`), so requiring it broke nothing and closed the trap
    before the first caller fell into it.

    Deterministic, no LLM. The subject/verb are the claim's own words (source
    language); this only phrases the conjunction between objects and the
    place distribution.

    #4649 fix: this used to print a bare COUNT ("witnessed 2 times") instead
    of the objects whenever count > 1 -- accurate but useless, since "2
    times" says nothing about WHAT. The objects are always listed now,
    joined by the language's own conjunction (`_REALISATION`); the count
    itself is redundant once every distinct object is named (the reader can
    count the list), so it is dropped rather than kept as decoration that
    could drift from the list beside it.
    """
    glue = _REALISATION.get(language, _REALISATION["en"])
    head = " ".join(part for part in (agg.subject, agg.verb) if part).strip()
    if agg.objects:
        objects = [_without_repeated_preposition(agg.verb, agg.objects[0], language), *agg.objects[1:]]
        body = f"{head} {_join_list(objects, glue['and'])}".strip()
    else:
        body = head
    if not body:
        return ""
    if agg.places:
        body = f"{body} ({glue['at']} {_join_list(agg.places, glue['and'])})"
    return body if body.endswith(".") else body + "."


# --- the entry composer (kg.read.biography, #4832; aggregation wired in #4839/#4649) --
#
# render_entry(db, entity_id) is the FIRST caller of stages 1/2/3/5/6 above, and the
# seam `kg.read.one-renderer` names as the target: the app is meant to draw sentences[]
# from this, replacing its own bespoke loops. Claims sharing a subject IDENTITY and a
# verb (and language -- see `aggregate_claims`) now merge into ONE sentence listing
# every distinct object; `claim_ids` grows to every contributing claim rather than
# staying trivially one-per-sentence.


def _entry_sort_key(claim: KnowledgeClaim) -> tuple[bool, str, object, str]:
    """claim date, then created_at, then id (team instruction) -- fully deterministic
    regardless of DB scan order, unlike `order_claims`'s stable-sort-preserves-input
    behavior for same-date claims."""
    start = claim.time_start
    if not start and claim.date_values:
        starts = [dv.start for dv in claim.date_values if dv.start]
        if starts:
            start = min(starts)
    return (not bool(start), start or "", claim.created_at, claim.id)


def _entity_role(claim: KnowledgeClaim, entity_id: str, entity_names: list[str]) -> str:
    """subject | object | mention -- which part the PAGE entity plays in `claim`.

    No object-entity link is stored at extraction time yet
    (`kg.read.object-slot-has-no-role` is an open, named GAP), so "object" is inferred
    here by checking whether the page entity's own canonical name or an alias appears
    in the claim's object phrase -- a pragmatic stand-in, not the eventual stored role.
    """
    if claim.subject_entity_id == entity_id:
        return "subject"
    obj = _claim_object(claim)
    if obj:
        obj_norm = _normalize(obj)
        # Whole-word match: a page for "Ana" is not the object of a claim
        # about "Anastasia".
        if any(
            name and re.search(rf"(?<!\w){re.escape(_normalize(name))}(?!\w)", obj_norm)
            for name in entity_names
        ):
            return "object"
    return "mention"


def _group_role(
    group_claims: list[KnowledgeClaim], entity_id: str, entity_names: list[str]
) -> str:
    """The page entity's role across every claim a merged sentence draws from.

    A merge groups on subject IDENTITY, so if the page entity IS that subject
    every member already says "subject" -- but when the page entity is not
    the subject, its role can still vary claim-to-claim (one merged object
    phrase may literally name it, another may not). "subject" wins over
    "object" wins over "mention", so a real involvement is never demoted to
    a generic mention just because one merged claim's object text didn't
    happen to repeat the page entity's name.
    """
    roles = {_entity_role(c, entity_id, entity_names) for c in group_claims}
    if "subject" in roles:
        return "subject"
    if "object" in roles:
        return "object"
    return "mention"


def _render_group_sentence(agg: "Aggregation", representative: KnowledgeClaim) -> str:
    """Realise one aggregation group into a sentence for `render_entry`.

    A group of one claim renders exactly as `_claim_sentence` always has --
    no behavior change for the common, unmerged case, and the fallback to
    the claim's own stored `text` when it has no complete S-V-O triple
    still applies. A group of MORE than one lists every distinct object,
    joined by the group's own language's conjunction (`_REALISATION`;
    unknown language falls back to the English glue table, same fallback
    `render_aggregation` already uses) -- never a bare count (#4649: a count
    is exactly what used to replace the objects), and never reworded: each
    object string is the claim's own extracted phrase, untouched.
    """
    if agg.count == 1:
        return _claim_sentence(representative)

    glue = _REALISATION.get(agg.language or "", _REALISATION["en"])
    joined_objects = _join_list(agg.objects, glue["and"])
    parts = order_statement_parts(agg.subject, agg.verb, joined_objects)
    if len(parts) >= 2:
        return _sentence_end(" ".join(parts))
    # No complete statement even after merging (e.g. no verb recognized at
    # all) -- fall back to the first contributing claim's own sentence
    # rather than silently dropping the whole group.
    return _claim_sentence(representative)


def render_entry(db, entity_id: str) -> list[dict]:
    """The entry composer -- ONE paragraph of `entity_id`'s claims, sentence-by-sentence,
    each carrying enough to make it clickable to its claim(s) and, later, to open its
    highlighted source (kg.read.sentence-opens-source-highlighted).

    Deterministic; calls no model. Each sentence states its OWN claim's true subject via
    the SAME subject/verb/object resolver `paragraph.py`'s renderer already uses
    (`_claim_sentence`, which reads `subject_canonical`/`svo_subject` -- the same fields
    the app's svoTriple reads) -- it never substitutes the page entity for a claim's real
    subject. Re-centring on the page's entity (ruling 2, #4837) is OUT of scope here:
    `revoiced` is always False, the seam that later work flips per-sentence once an
    inverse-phrasing table exists. A sentence renders in ITS OWN claim's source language
    (`source_languages[0]`; ``None`` when a claim carries none), never translated
    (ruling 4).

    Aggregation (stage 3, #4839/#4649) is now wired in: after ordering, claims are
    grouped by `aggregate_claims` -- same subject IDENTITY (entity id when known,
    never mere name-text), same verb, same language -- and each GROUP becomes one
    sentence. `claim_ids` on a merged sentence lists every contributing claim, in the
    order they were merged, so a click can still reach each one; no object is ever
    dropped (`_render_group_sentence`) or reworded (each is the claim's own extracted
    phrase); a merged sentence never claims an order or a causal link between its
    objects beyond what the language's plain conjunction ("y"/"and") states.

    Returns ``[]`` for an entity with no claims. `start`/`end` are character offsets into
    the paragraph these sentences join into (`" ".join(s["text"] for s in sentences)`),
    so a caller can always verify ``paragraph[s["start"]:s["end"]] == s["text"]``.
    """
    entity = db.get(KnowledgeEntity, entity_id)
    entity_names = [entity.canonical_name, *entity.aliases] if entity else []

    # Narrow at the query, same primitive `_claims_referencing_entity_ids`
    # (entity/entities.py) uses for "this entity's claims" elsewhere, then
    # apply the exact same subject-or-mention test as before -- no scan.
    # BOTH ways a claim belongs to an entity, matching `select_entry_claims`: it
    # is linked in `entity_ids`, OR it is the claim's subject. The two fields
    # drift in real libraries, so fetching by one alone silently drops claims.
    by_id = {
        c.id: c
        for c in (
            *db.query_json_list_intersects(KnowledgeClaim, "entity_ids", [entity_id]),
            *db.query(KnowledgeClaim, subject_entity_id=entity_id),
        )
    }
    candidates = list(by_id.values())
    claims = select_entry_claims(candidates, entity_id)
    claims = sorted(claims, key=_entry_sort_key)  # stage 2, before stage 3 aggregates

    sentences: list[dict] = []
    cursor = 0
    for group in aggregate_claims(claims):
        group_claims = [by_id[cid] for cid in group.claim_ids]
        representative = group_claims[0]
        text = _render_group_sentence(group, representative)
        if not text:
            continue
        start = cursor if not sentences else cursor + 1  # +1 for the joining space
        end = start + len(text)
        sentences.append(
            {
                "text": text,
                "start": start,
                "end": end,
                # None when the group's claims record no language: unknown
                # stays unknown, never a guessed label a later step would
                # trust. All members share this value -- it is IN the
                # aggregation key, so a mixed-language group cannot exist.
                "language": group.language,
                "claim_ids": list(group.claim_ids),
                "role": _group_role(group_claims, entity_id, entity_names),
                "revoiced": False,
            }
        )
        cursor = end
    return sentences
