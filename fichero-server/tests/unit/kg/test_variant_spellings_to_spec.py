"""Variant spellings of one entity are proposed for review, never merged (#4508), tested to the spec
(docs/contributor_manual/specs/kg/kg-tables.md): `kg.entity.variant-spellings-proposed`.

Through the public routes only: the dedupe check (`POST /api/kg/entity-curation/dedupe`) and the entity review
queue (`/api/kg/review/pairs`), over a real library. Nothing here is stubbed: there is no model in this path.
"""
from __future__ import annotations

import pytest

from fichero_server.models.knowledge import EntityCurationState, EntityType, KnowledgeEntity

DEDUPE = "/api/kg/entity-curation/dedupe"
PAIRS = "/api/kg/review/pairs"

#: Pairs the spec names as the same name written differently.
VARIANTS = [
    ("Mosquera", "Mosqera"),                    # old spelling: qu / q
    ("Isabel de Rojas", "Ysabel de Roxas"),     # y / i, x / j
    ("Jiménez", "Ximenez"),                     # accents, x / j
    ("Gonzalez", "Gonçalez"),                   # ç / z
    ("Vaca", "Baca"),                           # v / b
    ("Ortiz", "Hortiz"),                        # a silent h
    ("Rosales", "Rossales"),                    # a doubled letter
    ("Francisco Arboleda", "Fran.co Arboleda"),  # an abbreviation
    ("Cristóbal Mosquera", "Xpoval Mosquera"),   # an abbreviation
    ("Pedro González", "Pedro Glz"),             # an abbreviation
    ("Pedro Rodríguez", "Pº Rodz"),              # an abbreviation marked by a superscript, and a contraction
    ("Juan de Mosquera", "Don Juan de Mosquera"),  # a title
]


def _person(db, name, **kw):
    e = KnowledgeEntity(canonical_name=name, entity_type=kw.pop("entity_type", EntityType.person), **kw)
    db.save(e)
    return e


def _pairs(client):
    r = client.get(PAIRS, params={"limit": 500})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _names(group):
    return {group["survivor_name"], *group["absorbed_names"]}


@pytest.mark.parametrize("a,b", VARIANTS, ids=[f"{a}~{b}" for a, b in VARIANTS])
def test_kg_entity_variant_spellings_proposed__the_same_name_written_differently_is_found(client, db, a, b):
    """kg.entity.variant-spellings-proposed: "The same name written differently means equal once these are set
    aside: case, accents and punctuation; old spelling ...; the usual abbreviations of names ...; and titles"."""
    _person(db, a)
    _person(db, b)
    r = client.post(DEDUPE, json={"spelling_variants": True})
    assert r.status_code == 200, r.text
    groups = [g for g in r.json()["groups"] if g["basis"] == "spelling-variant"]
    assert [_names(g) for g in groups] == [{a, b}]


@pytest.mark.parametrize("a,b", [("Dredge No. 1", "Dredge No. 3"), ("Lot 1", "Lot 11"), ("Franco", "Francisco"), ("Pedro Franco", "Pedro Francisco"), ("Mosquera", "Mosquero"), ("Arboleda", "Arbolada"),
                                 ("Juan", "Juana")])
def test_kg_entity_variant_spellings_proposed__a_number_or_another_letter_is_never_set_aside(client, db, a, b):
    """kg.entity.variant-spellings-proposed: "A number is never set aside (`Dredge No. 1` and `Dredge No. 3` stay
    apart), nor is any other letter", and "an abbreviation is read as one only where it is written as one ...: a
    plain word is the word (the surname `Franco` is not `Fran.co`)"."""
    _person(db, a)
    _person(db, b)
    r = client.post(DEDUPE, json={"spelling_variants": True})
    assert r.json()["groups"] == []


def test_kg_entity_variant_spellings_proposed__one_type_only(client, db):
    """kg.entity.variant-spellings-proposed: "entities of one type": a person and a place spelled alike stay apart."""
    _person(db, "Mosquera")
    _person(db, "Mosqera", entity_type=EntityType.location)
    assert client.post(DEDUPE, json={"spelling_variants": True}).json()["groups"] == []


def test_kg_entity_variant_spellings_proposed__the_check_writes_nothing_until_asked_to_propose(client, db):
    """kg.entity.variant-spellings-proposed: "The check first answers with what it found (how many entities, how
    many groups, which names), writing nothing; asked to propose, it puts each pair into the entity review queue
    (method `name_variant`, with the two spellings in its reason) ... nothing is merged by the check."""
    survivor = _person(db, "Mosquera", corroboration_count=5)
    _person(db, "Mosqera")
    _person(db, "Mosquerra")
    _person(db, "Arboleda")

    found = client.post(DEDUPE, json={"spelling_variants": True}).json()
    assert found["dry_run"] is True and found["entity_count"] == 4 and found["duplicates_found"] == 2
    (group,) = found["groups"]
    assert group["survivor_name"] == "Mosquera" and sorted(group["absorbed_names"]) == ["Mosqera", "Mosquerra"]
    assert _pairs(client) == [], "finding writes nothing"

    proposed = client.post(DEDUPE, json={"spelling_variants": True, "propose": True}).json()
    assert proposed["proposals_queued"] == 2 and proposed["merges_applied"] == 0
    pairs = _pairs(client)
    assert {(p["survivor_name"], p["candidate_name"]) for p in pairs} == {("Mosquera", "Mosqera"),
                                                                          ("Mosquera", "Mosquerra")}
    assert {p["method"] for p in pairs} == {"name_variant"}
    assert all(p["candidate_name"] in p["reason"] and "Mosquera" in p["reason"] for p in pairs)
    live = [e for e in db.query(KnowledgeEntity) if e.merged_into_id is None]
    assert len(live) == 4, "nothing is merged by the check"
    assert all(p["survivor_entity_id"] == survivor.id for p in pairs)


def test_kg_entity_variant_spellings_proposed__a_decided_pair_is_never_proposed_again(client, db):
    """kg.entity.variant-spellings-proposed: "accepting is the audited merge and rejecting is remembered: a pair
    already proposed, accepted or rejected is never proposed again."""
    _person(db, "Mosquera", corroboration_count=5)
    _person(db, "Mosqera")
    _person(db, "Ysabel")
    _person(db, "Isabel", corroboration_count=5)
    assert client.post(DEDUPE, json={"spelling_variants": True, "propose": True}).json()["proposals_queued"] == 2
    assert client.post(DEDUPE, json={"spelling_variants": True, "propose": True}).json()["proposals_queued"] == 0

    by_name = {p["candidate_name"]: p for p in _pairs(client)}
    assert client.post(f"{PAIRS}/{by_name['Ysabel']['id']}/reject").status_code == 200
    assert client.post(f"{PAIRS}/{by_name['Mosqera']['id']}/accept").status_code == 200
    merged = [e for e in db.query(KnowledgeEntity) if e.merged_into_id]
    assert [e.canonical_name for e in merged] == ["Mosqera"], "accepting is the merge"

    again = client.post(DEDUPE, json={"spelling_variants": True, "propose": True}).json()
    assert again["proposals_queued"] == 0 and _pairs(client) == []


def test_kg_entity_variant_spellings_proposed__merging_them_in_bulk_is_refused(client, db):
    """kg.entity.variant-spellings-proposed: "Asking it to merge the variants itself is refused."""
    _person(db, "Mosquera")
    _person(db, "Mosqera")
    r = client.post(DEDUPE, json={"spelling_variants": True, "apply": True})
    assert r.status_code == 422, r.text
    assert all(e.merged_into_id is None for e in db.query(KnowledgeEntity))


def test_kg_entity_variant_spellings_proposed__curated_proposed_rejected_never(client, db):
    """kg.entity.variant-spellings-proposed: "Curated (reviewed) entities are proposed like any other, since a
    person decides each pair; rejected and already-merged ones never are."""
    _person(db, "Mosquera", curation_state=EntityCurationState.verified)
    _person(db, "Mosqera", curation_state=EntityCurationState.verified)
    _person(db, "Mosquerra", curation_state=EntityCurationState.rejected)
    (group,) = client.post(DEDUPE, json={"spelling_variants": True}).json()["groups"]
    assert _names(group) == {"Mosquera", "Mosqera"}


def test_kg_entity_variant_spellings_proposed__the_review_item_shows_both_names_in_full(client, db):
    """kg.entity.variant-spellings-proposed: "each pair ... with the two spellings in its reason", each shown in full
    as written, titles included, so a person sees `Don Juan de Mosquera` against `Juan de Mosquera`."""
    _person(db, "Juan de Mosquera", corroboration_count=5)
    _person(db, "Don Juan de Mosqera")
    client.post(DEDUPE, json={"spelling_variants": True, "propose": True})
    (pair,) = _pairs(client)
    assert (pair["survivor_name"], pair["candidate_name"]) == ("Juan de Mosquera", "Don Juan de Mosqera")
    assert "'Don Juan de Mosqera'" in pair["reason"] and "'Juan de Mosquera'" in pair["reason"], pair["reason"]


def test_kg_entity_variant_spellings_proposed__only_direct_pairs_each_with_its_own_basis(client, db):
    """kg.entity.variant-spellings-proposed: "each pair of entities whose own names match, never two that are only
    joined through a third (an entity holding a stray name of a second, which is a variant of a third, does not
    make the first and third a pair); each pair says why ... in its method: `name_variant` for a spelling variant,
    `duplicate_name` for the same name or a name both hold"."""
    _person(db, "Jose Dionisio de Villar", aliases=["francisco de paz"], corroboration_count=9)
    _person(db, "Francisco de Paz", corroboration_count=5)
    _person(db, "Francisco de Pas")
    proposed = client.post(DEDUPE, json={"spelling_variants": True, "propose": True}).json()
    pairs = {frozenset((p["survivor_name"], p["candidate_name"])): p for p in _pairs(client)}
    assert set(pairs) == {frozenset(("Jose Dionisio de Villar", "Francisco de Paz")),
                          frozenset(("Francisco de Paz", "Francisco de Pas"))}, set(pairs)
    assert proposed["proposals_queued"] == 2
    assert pairs[frozenset(("Jose Dionisio de Villar", "Francisco de Paz"))]["method"] == "duplicate_name"
    assert pairs[frozenset(("Francisco de Paz", "Francisco de Pas"))]["method"] == "name_variant"
    assert "written differently" not in pairs[frozenset(("Jose Dionisio de Villar", "Francisco de Paz"))]["reason"]
