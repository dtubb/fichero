"""A statement's place is said once, with its basis, and links a known name (#6838).

spec: kg-paragraph-realisation (`kg.para.place-stated-once`, `kg.para.place-says-its-basis`,
`kg.para.place-links-its-name`)
"""
from __future__ import annotations

import pytest

from fichero_server.knowledge.readable import render_entry_with_mentions
from fichero_server.models.knowledge import (
    EvidenceBasis,
    EvidentialPlace,
    KnowledgeClaim,
    KnowledgeEntity,
    RelativePlace,
)

PAGE = "ent-ines"


class _Db:
    def __init__(self, claims, known=()):
        self.claims = claims
        self.known = {e.canonical_name: e for e in known}
        self.entity = KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel")
        self.lookups: list[list[str]] = []

    def get(self, model, key):
        return self.entity

    def query_json_list_intersects(self, model, field, values):
        return list(self.claims)

    def query(self, model, **kw):
        assert model is not KnowledgeEntity, "a place name is looked up through entity_ids_by_canonical_name"
        return []

    def entity_ids_by_canonical_name(self, names):
        self.lookups.append(sorted(names))
        return {n: [self.known[n].id] for n in names if n in self.known}


def _claim(cid, verb, obj, lang="en", **kw) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid, text=f"Inés Valcárcel {verb} {obj}", svo_subject="Inés Valcárcel", svo_verb=verb,
        svo_object=obj, subject_entity_id=PAGE, entity_ids=[PAGE], source_languages=[lang], **kw)


def _read(claims, known=()):
    return render_entry_with_mentions(_Db(claims, known), PAGE)[0]


def test_a_place_is_said_once_and_names_all_it_qualifies():
    claims = [
        _claim("c1", "sold", "a horse", claim_location="Quito"),
        _claim("c2", "sold", "an ox", place_values=[EvidentialPlace(label="Quito", basis=EvidenceBasis.asserted)]),
        _claim("c3", "sold", "a mule", claim_location="Quito"),
    ]
    sentence = _read(claims)[0]
    assert sentence["text"] == "Inés Valcárcel sold a horse, an ox and a mule in Quito."
    place = [g for g in sentence["segments"] if g["start"] == sentence["text"].index("in Quito")]
    assert len(place) == 1 and place[0]["claim_ids"] == ["c1", "c2", "c3"]
    assert place[0]["origin"] == "claim:c1:claim_location"


def test_a_single_statement_says_its_place_after_its_object_and_es_in_spanish():
    en = _read([_claim("c1", "sold", "a horse", claim_location="Quito")])[0]
    assert en["text"] == "Inés Valcárcel sold a horse in Quito."
    es = _read([_claim("c1", "vendió", "un caballo", "es", claim_location="Quito")])[0]
    assert es["text"] == "Inés Valcárcel vendió un caballo en Quito."
    assert es["clauses"][0]["place"]["text"] == "en Quito"


def test_a_place_the_object_already_says_is_not_said_again():
    sentence = _read([_claim("c1", "sold", "a house in Quito", claim_location="Quito")])[0]
    assert sentence["text"] == "Inés Valcárcel sold a house in Quito."
    assert sentence["clauses"][0]["place"] is None


def test_a_statement_with_no_place_says_none():
    sentence = _read([_claim("c1", "sold", "a horse")])[0]
    assert sentence["text"] == "Inés Valcárcel sold a horse."
    assert sentence["clauses"][0]["place"] is None


@pytest.mark.parametrize("basis,en,es", [
    (EvidenceBasis.asserted, "Inés Valcárcel sold a horse in Quito.", "Inés Valcárcel vendió un caballo en Quito."),
    (EvidenceBasis.source_anchored, "Inés Valcárcel sold a horse (in a document drawn up in Quito).",
     "Inés Valcárcel vendió un caballo (en un documento redactado en Quito)."),
    (EvidenceBasis.inferred, "Inés Valcárcel sold a horse in Quito (place inferred).",
     "Inés Valcárcel vendió un caballo en Quito (lugar inferido)."),
])
def test_a_documents_place_is_not_said_as_the_events_place(basis, en, es):
    values = [EvidentialPlace(label="Quito", basis=basis)]
    assert _read([_claim("c1", "sold", "a horse", place_values=values)])[0]["text"] == en
    assert _read([_claim("c1", "vendió", "un caballo", "es", place_values=values)])[0]["text"] == es
    clause = _read([_claim("c1", "sold", "a horse", place_values=values)])[0]["clauses"][0]
    assert clause["place"]["basis"] == basis.value


def test_a_place_given_relative_to_another_is_said_as_written():
    rel = RelativePlace(anchor_entity_id="ent-q", relation_as_written="de", distance_as_written="21 leguas", distance_value=21, unit="legua")
    values = [EvidentialPlace(label="21 leguas de Quito", basis=EvidenceBasis.asserted, relative=rel)]
    sentence = _read([_claim("c1", "vendió", "un caballo", "es", place_values=values)])[0]
    assert sentence["text"] == "Inés Valcárcel vendió un caballo a 21 leguas de Quito."
    assert sentence["clauses"][0]["place"]["text"] == "a 21 leguas de Quito"


def test_a_known_place_carries_its_entity_id():
    quito = KnowledgeEntity(id="ent-quito", canonical_name="Quito")
    known = _read([_claim("c1", "sold", "a horse", claim_location="Quito")], known=[quito])[0]
    assert known["clauses"][0]["place"]["entity_id"] == "ent-quito"
    unknown = _read([_claim("c1", "sold", "a horse", claim_location="Quito")])[0]
    assert unknown["clauses"][0]["place"]["entity_id"] is None


def test_the_route_model_takes_a_clause_place_as_the_engine_gives_it():
    from fichero_server.api.routes.kg.render import ReadableSentence

    quito = KnowledgeEntity(id="ent-quito", canonical_name="Quito")
    sentence = _read([_claim("c1", "vendió", "un caballo", "es", claim_location="Quito")], known=[quito])[0]
    place = ReadableSentence(**sentence).clauses[0].place
    assert (place.text, place.label, place.entity_id) == ("en Quito", "Quito", "ent-quito")


def test_every_place_of_an_entry_is_looked_up_in_one_call():
    db = _Db([
        _claim("c1", "sold", "a horse", claim_location="Quito"),
        _claim("c2", "bought", "an ox", claim_location="Lima"),
        _claim("c3", "witnessed", "a will", claim_location="Cali"),
    ], known=[KnowledgeEntity(id="ent-lima", canonical_name="Lima")])
    sentences = render_entry_with_mentions(db, PAGE)[0]
    assert db.lookups == [["Cali", "Lima", "Quito"]]
    assert [s["clauses"][0]["place"]["entity_id"] for s in sentences] == [None, "ent-lima", None]


def test_the_database_returns_every_entity_of_a_canonical_name(db):
    db.save_many([
        KnowledgeEntity(id="ent-quito", canonical_name="Quito"),
        KnowledgeEntity(id="ent-lima-1", canonical_name="Lima"),
        KnowledgeEntity(id="ent-lima-2", canonical_name="Lima"),
        KnowledgeEntity(id="ent-cali", canonical_name="Cali", aliases=["Santiago"]),
    ], new=True)
    found = db.entity_ids_by_canonical_name(["Quito", "Lima", "Santiago", "quito"])
    assert found == {"Quito": ["ent-quito"], "Lima": ["ent-lima-1", "ent-lima-2"]}


def test_a_real_entry_links_one_known_place_and_not_a_shared_name(db):
    db.save_many([
        KnowledgeEntity(id=PAGE, canonical_name="Inés Valcárcel"),
        KnowledgeEntity(id="ent-quito", canonical_name="Quito"),
        KnowledgeEntity(id="ent-lima-1", canonical_name="Lima"),
        KnowledgeEntity(id="ent-lima-2", canonical_name="Lima"),
    ], new=True)
    db.save_many([
        _claim("c1", "sold", "a horse", claim_location="Quito"),
        _claim("c2", "bought", "an ox", claim_location="Lima"),
    ], new=True)
    sentences = render_entry_with_mentions(db, PAGE)[0]
    assert {s["clauses"][0]["place"]["label"]: s["clauses"][0]["place"]["entity_id"] for s in sentences} == {
        "Quito": "ent-quito", "Lima": None}
