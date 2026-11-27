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

import json
import re
import unicodedata

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from fichero_server.knowledge._common import STATEMENT_ROLE_ORDER, order_statement_parts
from fichero_server.knowledge.paragraph import (
    _claim_object,
    _claim_sentence,
    _claim_subject,
    _claim_verb,
    _normalize,
    _sentence_end,
)
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EpistemicStatus,
    EvidenceBasis,
    KnowledgeClaim,
    KnowledgeEntity,
)


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
    table = _TABLES.get(language)
    if table is None:
        return False
    first_word = obj.strip().split(" ", 1)[0]
    if not first_word:
        return False
    return _fold(first_word) in table["prepositions"]


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
    if _claim_language(claim) not in _TABLES:
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


# Stage 6 — realisation. A language's words are one JSON file in `resources/language_tables/`
# (`<language>.json`), read once at import and validated: joining word, place word, count word,
# leading prepositions and contractions. The verb + objects come from the claim's own SVO (already
# in the source's language — we never translate). Add a language by adding a file; a language with
# no file is never joined (`_is_solo_claim`) and takes no word from another language.
LANGUAGE_TABLES_DIR = Path(__file__).resolve().parent.parent / "resources" / "language_tables"
_TABLE_STRINGS = ("and", "at", "times")


_DATE_PATTERNS = ("day", "month", "year", "span", "about", "after", "before")


def _check_date_words(name: str, dates: object) -> None:
    """A table's `dates` is the seven level patterns, `inferred` (holding `{date}`), `undated` and twelve month names."""
    if not isinstance(dates, dict):
        raise ValueError(f"{name}: dates must be an object")
    for key in (*_DATE_PATTERNS, "inferred", "undated"):
        if not isinstance(dates.get(key), str) or not dates[key]:
            raise ValueError(f"{name}: dates.{key} must be a non-empty string")
    if "{date}" not in dates["inferred"]:
        raise ValueError(f"{name}: dates.inferred must hold {{date}}")
    months = dates.get("months")
    if not isinstance(months, list) or len(months) != 12 or not all(isinstance(m, str) and m for m in months):
        raise ValueError(f"{name}: dates.months must be twelve names")


_PLACE_WORDS = ("at", "document", "inferred", "relative")


def _check_place_words(name: str, places: object) -> None:
    """A table's `places` is four patterns, each holding `{place}`."""
    if not isinstance(places, dict):
        raise ValueError(f"{name}: places must be an object")
    for key in _PLACE_WORDS:
        if not isinstance(places.get(key), str) or "{place}" not in places[key]:
            raise ValueError(f"{name}: places.{key} must be a string holding {{place}}")


def load_language_tables(directory: Path) -> dict[str, dict]:
    """Every `<language>.json` in `directory`, keyed by language; a file with a missing or mistyped
    key, or named for a language other than its own `language` field, raises ValueError."""
    tables: dict[str, dict] = {}
    for path in sorted(Path(directory).glob("*.json")):
        table = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(table, dict) or table.get("language") != path.stem:
            raise ValueError(f"{path.name}: `language` must be {path.stem!r}")
        if not all(isinstance(table.get(k), str) and table[k] for k in _TABLE_STRINGS):
            raise ValueError(f"{path.name}: {', '.join(_TABLE_STRINGS)} must be non-empty strings")
        prepositions = table.get("prepositions")
        if not isinstance(prepositions, list) or not all(isinstance(w, str) and w for w in prepositions):
            raise ValueError(f"{path.name}: prepositions must be a list of words")
        contractions = table.get("contractions")
        if not isinstance(contractions, dict) or not all(
            isinstance(k, str) and len(k.split()) == 2 and isinstance(v, str) and v for k, v in contractions.items()
        ):
            raise ValueError(f"{path.name}: contractions must map two words to one")
        places = table.get("places")
        if places is not None:
            _check_place_words(path.name, places)
        dates = table.get("dates")
        if dates is not None:
            _check_date_words(path.name, dates)
        tables[path.stem] = {
            **table,
            "prepositions": {_fold(w) for w in prepositions},
            "contractions": {_fold(k): v for k, v in contractions.items()},
        }
    return tables


_TABLES = load_language_tables(LANGUAGE_TABLES_DIR)

_DATE_PARTS = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")


def _claim_date(claim: KnowledgeClaim, language: str | None) -> dict | None:
    """The date of `claim` in `language`'s table as {text, level, basis, as_written}; None when the
    claim has no readable date or the language's table holds no date words.

    The point is `time_start` (with `time_end`, `time_precision`), else the first date value. The
    level is the one held, never finer: a start with no stored level is a year; `circa`, `open_end`
    and `open_start` of that date value are read as the table's about / after / before rows (said at
    the year); a start and end in different years is a span. A date value whose basis is inferred is
    followed by the table's inferred words. `as_written` is that date value's label.
    """
    words = (_TABLES.get(language or "") or {}).get("dates")
    if not words:
        return None
    value = claim.date_values[0] if claim.date_values else None
    if claim.time_start:
        start, end, precision = claim.time_start, claim.time_end, claim.time_precision
        if value is not None and value.start != claim.time_start:
            value = None
    elif value is not None and value.start:
        start, end, precision = value.start, value.end, value.precision
    else:
        return None
    parts = _DATE_PARTS.match(start)
    if not parts:
        return None
    year, month, day = parts.group(1), parts.group(2), parts.group(3)
    end_year = (_DATE_PARTS.match(end).group(1) if end and _DATE_PARTS.match(end) else year)
    if value is not None and value.circa:
        level = "about"
    elif value is not None and value.open_end:
        level = "after"
    elif value is not None and value.open_start:
        level = "before"
    elif end_year != year:
        level = "span"
    elif precision == "day" and month and day:
        level = "day"
    elif precision == "month" and month:
        level = "month"
    else:
        level = "year"
    month_name = words["months"][int(month) - 1] if month and 1 <= int(month) <= 12 else ""
    if level in ("day", "month") and not month_name:
        level = "year"
    text = words[level].format(year=str(int(year)), end_year=str(int(end_year)), month=month_name, day=str(int(day or 0)))
    inferred = value is not None and value.basis == EvidenceBasis.inferred
    if inferred:
        text = words["inferred"].format(date=text)
    return {
        "text": text,
        "level": level,
        "basis": value.basis.value if value is not None else None,
        "as_written": value.label if value is not None else None,
    }


def _claim_place(claim: KnowledgeClaim, language: str | None) -> dict | None:
    """The place of `claim` in `language`'s table as {text, label, basis, entity_id, origin}; None when
    the claim has no place, the table holds no place words, or the object already says the place.

    The place is `claim_location`, else the first place value's label. The basis is that place value's
    when it is the one read (its label is the location, or there is no location). A place value
    that is relative to another is said as written after the table's relative word; a basis
    source-anchored is said as the document's place, an inferred one with the inferred words,
    anything else plainly. `entity_id` is filled by the caller.
    """
    words = (_TABLES.get(language or "") or {}).get("places")
    if not words:
        return None
    value = claim.place_values[0] if claim.place_values else None
    label = " ".join((claim.claim_location or (value.label if value else "")).split())
    if not label:
        return None
    read = value if value is not None and (not claim.claim_location or value.label == claim.claim_location) else None
    if _fold(label) in _fold(_claim_object(claim) or ""):
        return None
    if read is not None and read.relative is not None:
        kind = "relative"
    elif read is not None and read.basis == EvidenceBasis.source_anchored:
        kind = "document"
    elif read is not None and read.basis == EvidenceBasis.inferred:
        kind = "inferred"
    else:
        kind = "at"
    return {
        "text": words[kind].format(place=label),
        "label": label,
        "basis": read.basis.value if read is not None else None,
        "entity_id": None,
        "origin": f"claim:{claim.id}:{'claim_location' if claim.claim_location else 'place_values'}",
    }


def _date_origin(claim: KnowledgeClaim) -> str:
    return f"claim:{claim.id}:{'time_start' if claim.time_start else 'date_values'}"


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
    table = _TABLES.get(language or "", {}).get("prepositions", set())
    last = _fold(verb.split()[-1]) if verb.split() else ""
    first, _, rest = obj.strip().partition(" ")
    if rest and last in table and _fold(first) == last:
        return rest.strip()
    return obj


def _seam(verb: str, obj: str, language: str | None, *, contract: bool) -> tuple[str, str | None, str, str]:
    """The seam of a verb and its object in `language`'s table: (verb, contraction, object, contraction
    key). A preposition ending the verb and starting the object is said once (the object's copy is
    dropped); with `contract`, a verb ending in a table's first word and an object starting with its
    second ("de" + "el") become the table's contraction ("del") with both words dropped from their
    pieces. Each returned piece is a part of the stored text, left whole when the table has no say."""
    table = _TABLES.get(language or "")
    verb_words, obj_words = verb.split(), obj.split()
    if table is None or not verb_words or len(obj_words) < 2:
        return verb, None, obj, ""
    last, first = _fold(verb_words[-1]), _fold(obj_words[0])
    if contract and len(verb_words) > 1 and f"{last} {first}" in table["contractions"]:
        return " ".join(verb_words[:-1]), table["contractions"][f"{last} {first}"], " ".join(obj_words[1:]), f"{last} {first}"
    if last in table["prepositions"] and first == last:
        return verb, None, " ".join(obj_words[1:]), ""
    return verb, None, obj, ""


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
    joined by the language's own conjunction (`_TABLES`); the count
    itself is redundant once every distinct object is named (the reader can
    count the list), so it is dropped rather than kept as decoration that
    could drift from the list beside it.
    """
    glue = _TABLES.get(language, _TABLES["en"])
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
    joined by the group's own language's conjunction (`_TABLES`;
    unknown language falls back to the English glue table, same fallback
    `render_aggregation` already uses) -- never a bare count (#4649: a count
    is exactly what used to replace the objects), and never reworded: each
    object string is the claim's own extracted phrase, untouched.
    """
    if agg.count == 1:
        return _claim_sentence(representative)

    glue = _TABLES.get(agg.language or "", _TABLES["en"])
    joined_objects = _join_list(agg.objects, glue["and"])
    parts = order_statement_parts(agg.subject, agg.verb, joined_objects)
    if len(parts) >= 2:
        return _sentence_end(" ".join(parts))
    # No complete statement even after merging (e.g. no verb recognized at
    # all) -- fall back to the first contributing claim's own sentence
    # rather than silently dropping the whole group.
    return _claim_sentence(representative)


_ROLE_FIELDS = {
    "subject": ("subject_canonical", "svo_subject"),
    "verb": ("predicate_verb", "svo_verb"),
    "object": ("object_phrase", "svo_object"),
}


def _role_field(claim: KnowledgeClaim, role: str) -> str:
    """The stored field the claim's `role` text comes from (the first one set, as `_claim_subject` etc. read)."""
    return next(name for name in _ROLE_FIELDS[role] if getattr(claim, name))


def _claim_pieces(claim: KnowledgeClaim) -> list[tuple[str, str]]:
    """`_claim_sentence` as (text, origin) pieces joined by single spaces, a "." piece last when added.

    A piece's text is the stored field with whitespace collapsed, or a part of it where the language's
    table fixes the seam of verb and object (`_seam`). A statement in a language with no table keeps
    the year of its start date, in digits and brackets, after the object.
    """
    values = {
        "subject": _claim_subject(claim),
        "verb": _claim_verb(claim),
        "object": _claim_object(claim),
    }
    lang = _claim_language(claim)
    pieces: list[tuple[str, str]] = []
    if values["verb"] and values["object"]:
        verb, contraction, obj, key = _seam(values["verb"], values["object"], lang, contract=True)
        values = {**values, "verb": verb, "object": obj}
        contraction_piece = [(contraction, f"table:{lang}:{key}")] if contraction else []
    else:
        contraction_piece = []
    for role in STATEMENT_ROLE_ORDER:
        if values[role]:
            pieces.append((values[role], f"claim:{claim.id}:{_role_field(claim, role)}"))
            if role == "verb":
                pieces.extend(contraction_piece)
    if len(pieces) < 2:
        text = " ".join(claim.text.split())
        if text:
            pieces = [(text, f"claim:{claim.id}:text")]
    date = _claim_date(claim, lang)
    if pieces and date:
        pieces.insert(0, (f"{date['text'][0].upper()}{date['text'][1:]},", _date_origin(claim)))
    place = _claim_place(claim, lang)
    if pieces and place:
        pieces.append((place["text"], place["origin"]))
    year = (claim.time_start or "")[:4]
    if pieces and lang not in _TABLES and year.isdigit():
        pieces.append((f"({year})", f"claim:{claim.id}:time_start"))
    if pieces and not pieces[-1][0].endswith((".", "!", "?")):
        pieces.append((".", "punctuation"))
    return pieces


def _join_pieces(pieces: list[tuple[str, str, list[str]]]) -> tuple[str, list[dict]]:
    """Text and segments (offsets within the text) from the same pieces. A piece starting with "." or ","
    is attached without a space."""
    text = ""
    segments: list[dict] = []
    for piece, origin, ids in pieces:
        if text and not piece.startswith((".", ",")):
            text += " "
        start = len(text)
        text += piece
        segments.append({"start": start, "end": len(text), "origin": origin, "claim_ids": list(ids)})
    return text, segments


def _group_state(claims: list[KnowledgeClaim]) -> str:
    reviewed = all(
        c.curation_state == ClaimCurationState.curated or c.epistemic_status == EpistemicStatus.confirmed
        for c in claims
    )
    return "reviewed" if reviewed else "proposed"


def _sources(claims: list[KnowledgeClaim]) -> int:
    return len({d for c in claims for d in (c.source_document_id, *c.source_ids) if d})


def _merged_pieces(
    agg: "Aggregation", group_claims: list[KnowledgeClaim]
) -> tuple[list[tuple[str, str, list[str]]], list[tuple[int, list[KnowledgeClaim], int]]] | None:
    """The pieces of a merged sentence as `_render_group_sentence` joins them, and (index of the object
    piece, claims, index of the last piece of the object) per distinct object, whose date, when it has
    one, follows it in brackets; None when the group has no complete statement. A place every statement
    has is said once at the end; otherwise each object's own places follow it, before its date."""
    ids = list(agg.claim_ids)
    first = group_claims[0]
    lang = agg.language if agg.language in _TABLES else "en"
    objects = [(obj, [c for c in group_claims if _claim_object(c) == obj]) for obj in agg.objects]
    if objects:
        objects[0][1].extend(c for c in group_claims if not _claim_object(c))
    head = [
        (agg.subject, f"claim:{first.id}:{_role_field(first, 'subject')}", ids) if agg.subject else None,
        (agg.verb, f"claim:{first.id}:{_role_field(first, 'verb')}", ids) if agg.verb else None,
    ]
    pieces = [p for p in head if p]
    if len(pieces) + bool(objects) < 2:
        return None
    marks: list[tuple[int, list[KnowledgeClaim], int]] = []
    # a place every statement shares is said once at the end; otherwise each object is followed by its own
    texts = {(_claim_place(c, lang) or {}).get("text") for c in group_claims}
    one_place = len(texts) == 1 and None not in texts
    for i, (obj, members) in enumerate(objects):
        if agg.verb:
            verb, contraction, shown, key = _seam(agg.verb, obj, lang, contract=i == 0)
            if i == 0 and contraction:
                pieces[-1] = (verb, pieces[-1][1], ids)
                pieces.append((contraction, f"table:{lang}:{key}", ids))
        else:
            shown = obj
        if i == len(objects) - 1 and i:
            pieces.append((_TABLES[lang]["and"], f"table:{lang}:and", ids))
        elif i:
            pieces.append((",", "punctuation", ids))
        pieces.append((shown, f"claim:{members[0].id}:{_role_field(members[0], 'object')}", [m.id for m in members]))
        at = len(pieces) - 1
        if not one_place:
            pieces.extend(_place_pieces(members, lang, ids))
        date = _claim_date(members[0], lang)
        if date:
            pieces.append((f"({date['text']})", _date_origin(members[0]), [m.id for m in members]))
        marks.append((at, members, len(pieces) - 1))
    if one_place:
        pieces.extend(_place_pieces(group_claims, lang, ids))
    if not pieces[-1][0].endswith((".", "!", "?")):
        pieces.append((".", "punctuation", ids))
    return pieces, marks


def _place_pieces(claims: list[KnowledgeClaim], lang: str, ids: list[str]) -> list[tuple[str, str, list[str]]]:
    """Each distinct place of `claims`, once, joined by the table's list words; its piece names every claim that has it."""
    shared: dict[str, tuple[str, list[KnowledgeClaim]]] = {}
    for c in claims:
        place = _claim_place(c, lang)
        if place:
            shared.setdefault(place["text"], (place["origin"], []))[1].append(c)
    pieces: list[tuple[str, str, list[str]]] = []
    for i, (text, (origin, members)) in enumerate(shared.items()):
        if i and i == len(shared) - 1:
            pieces.append((_TABLES[lang]["and"], f"table:{lang}:and", ids))
        elif i:
            pieces.append((",", "punctuation", ids))
        pieces.append((text, origin, [m.id for m in members]))
    return pieces


def _trace_group_sentence(
    agg: "Aggregation", group_claims: list[KnowledgeClaim], entity_id: str, entity_names: list[str]
) -> tuple[str, list[dict], list[dict]]:
    """The sentence of `_render_group_sentence`, with its clauses and segments (offsets within the sentence).

    A single claim, or a group with no complete statement, is one clause with all the group's claim ids.
    A merged group has one clause per distinct object phrase; a claim with no object joins the first.
    """
    ids = list(agg.claim_ids)
    merged = _merged_pieces(agg, group_claims) if agg.count > 1 else None
    if merged is None:
        pieces = [(t, o, ids) for t, o in _claim_pieces(group_claims[0])]
        marks: list[tuple[int, list[KnowledgeClaim], int]] = []
    else:
        pieces, marks = merged
    text, segments = _join_pieces(pieces)
    spans = [(segments[i]["start"], segments[j]["end"], m) for i, m, j in marks] if len(marks) > 1 else [
        (0, len(text), group_claims)
    ]
    clauses = [
        {
            "start": start,
            "end": end,
            "claim_ids": [c.id for c in members],
            "role": _group_role(members, entity_id, entity_names),
            "revoiced": False,
            "state": _group_state(members),
            "doubt": "none",
            "sources": _sources(members),
            "date": _claim_date(members[0], agg.language),
            "place": {k: v for k, v in (_claim_place(members[0], agg.language) or {}).items() if k != "origin"} or None,
        }
        for start, end, members in spans
    ]
    return text, clauses, segments


def _is_withdrawn(claim: KnowledgeClaim) -> bool:
    """A statement a person rejected, or one merged into another: said nowhere."""
    return (
        claim.curation_state == ClaimCurationState.rejected
        or claim.epistemic_status == EpistemicStatus.rejected
        or bool(claim.merged_into_id)
    )


def render_entry(db, entity_id: str) -> list[dict]:
    """The sentences of `render_entry_with_mentions`; see it."""
    return render_entry_with_mentions(db, entity_id)[0]


def render_entry_with_mentions(db, entity_id: str) -> tuple[list[dict], list[dict]]:
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

    A statement a person rejected (`curation_state` or `epistemic_status`), or one merged into
    another (`merged_into_id`), is in neither result. A statement in which the page entity is
    neither subject nor object (role ``mention``) is not narrated: it is the second result, a
    list of ``{claim_id, text, document_id}`` in the paragraph's order.

    Returns ``([], [])`` for an entity with no claims. `start`/`end` are character offsets into
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
    claims = [c for c in select_entry_claims(candidates, entity_id) if not _is_withdrawn(c)]
    claims = sorted(claims, key=_entry_sort_key)  # stage 2, before stage 3 aggregates
    mention_claims = [c for c in claims if _entity_role(c, entity_id, entity_names) == "mention"]
    mentioned = {c.id for c in mention_claims}
    mentions = [
        {"claim_id": c.id, "text": _claim_sentence(c), "document_id": c.source_document_id}
        for c in mention_claims
    ]
    claims = [c for c in claims if c.id not in mentioned]

    sentences: list[dict] = []
    cursor = 0
    said_a_date = False
    said_undated = False
    places: list[dict] = []
    for group in aggregate_claims(claims):
        group_claims = [by_id[cid] for cid in group.claim_ids]
        text, clauses, segments = _trace_group_sentence(group, group_claims, entity_id, entity_names)
        if not text:
            continue
        places.extend(c["place"] for c in clauses if c["place"])
        dated = any(c["date"] for c in clauses)
        undated_words = ((_TABLES.get(group.language or "") or {}).get("dates") or {}).get("undated")
        if said_a_date and not said_undated and not dated and undated_words:
            # the first undated sentence after dated ones opens with the table's undated words
            shift = len(undated_words) + 1
            text = f"{undated_words} {text}"
            clauses = [{**c, "start": c["start"] + shift, "end": c["end"] + shift} for c in clauses]
            segments = [
                {"start": 0, "end": len(undated_words), "origin": f"table:{group.language}:undated", "claim_ids": list(group.claim_ids)},
                *({**g, "start": g["start"] + shift, "end": g["end"] + shift} for g in segments),
            ]
            said_undated = True
        said_a_date = said_a_date or dated
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
                "clauses": [{**c, "start": start + c["start"], "end": start + c["end"]} for c in clauses],
                "segments": [{**g, "start": start + g["start"], "end": start + g["end"]} for g in segments],
            }
        )
        cursor = end
    if places:
        # one lookup for every place of the entry; a name held by exactly one entity links to it
        known = db.entity_ids_by_canonical_name([p["label"] for p in places])
        for place in places:
            found = known.get(place["label"], [])
            place["entity_id"] = found[0] if len(found) == 1 else None
    return sentences, mentions
