"""Coverage for the RDF triple substrate ``fichero.knowledge.triples`` (#899),
previously untested. Pure logic (rdflib in-memory graph; ``persist`` writes to
tmp_path — no network/DB). Pins URI minting, the EntityType->ontology-class map,
entity/claim triple emission (structured SVO vs unstructured), and the
build/persist/sparql round-trip.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, Literal, RDF, RDFS
from rdflib.namespace import FOAF, SKOS

from fichero.knowledge import triples as T
from fichero.knowledge.triples import FICHERO, SCHEMA
from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity


def _entity(**kw) -> KnowledgeEntity:
    kw.setdefault("canonical_name", "X")
    kw.setdefault("entity_type", EntityType.person)
    return KnowledgeEntity(**kw)


def _claim(**kw) -> KnowledgeClaim:
    kw.setdefault("text", "some claim")
    kw.setdefault("source_document_id", "d1")
    return KnowledgeClaim(**kw)


# ===========================================================================
# URI minting
# ===========================================================================


def test_uris_are_stable_and_quoted():
    assert str(T._entity_uri("e1")) == "https://fichero.app/entity/e1"
    assert str(T._claim_uri("c1")) == "https://fichero.app/claim/c1"
    assert str(T._doc_uri("d1")) == "https://fichero.app/document/d1"
    # Unsafe characters are percent-encoded so the URI stays valid.
    assert str(T._entity_uri("a/b c")) == "https://fichero.app/entity/a%2Fb%20c"


# ===========================================================================
# EntityType -> ontology class
# ===========================================================================


@pytest.mark.parametrize(
    "etype,expected",
    [
        (EntityType.person, FOAF.Person),
        (EntityType.location, SCHEMA.Place),
        (EntityType.organization, SCHEMA.Organization),
        (EntityType.event, SCHEMA.Event),
        (EntityType.concept, SKOS.Concept),
        (EntityType.other, SCHEMA.Thing),
        (EntityType.citation, SCHEMA.Thing),  # unmapped -> Thing fallback
    ],
)
def test_entity_type_class_mapping(etype, expected):
    assert T._entity_type_class(etype) == expected


# ===========================================================================
# make_graph — prefix bindings
# ===========================================================================


def test_make_graph_binds_prefixes():
    g = T.make_graph()
    bound = {prefix for prefix, _ in g.namespaces()}
    assert {"fichero", "foaf", "schema", "skos", "rdfs", "rdf"} <= bound


# ===========================================================================
# entity_to_triples
# ===========================================================================


def test_entity_triples_full():
    g = T.make_graph()
    e = _entity(id="e1", canonical_name="Juan Pérez", entity_type=EntityType.person,
                aliases=["Perez", "J. Pérez"], description="a notary", language="es")
    T.entity_to_triples(g, e)
    uri = T._entity_uri("e1")
    assert (uri, RDF.type, FOAF.Person) in g
    assert (uri, RDFS.label, Literal("Juan Pérez", lang="es")) in g
    assert (uri, SKOS.altLabel, Literal("Perez")) in g
    assert (uri, SKOS.altLabel, Literal("J. Pérez")) in g
    assert (uri, RDFS.comment, Literal("a notary")) in g


def test_entity_label_without_language_has_no_lang_tag():
    g = T.make_graph()
    T.entity_to_triples(g, _entity(id="e1", canonical_name="Plain", language=None))
    assert (T._entity_uri("e1"), RDFS.label, Literal("Plain")) in g


def test_entity_no_description_no_comment():
    g = T.make_graph()
    T.entity_to_triples(g, _entity(id="e1", canonical_name="NoDesc", description=None))
    assert list(g.triples((T._entity_uri("e1"), RDFS.comment, None))) == []


def test_entity_merged_into_edge():
    g = T.make_graph()
    T.entity_to_triples(g, _entity(id="e1", canonical_name="Dup", merged_into_id="e2"))
    assert (T._entity_uri("e1"), FICHERO.mergedInto, T._entity_uri("e2")) in g


# ===========================================================================
# _predicate_uri
# ===========================================================================


def test_predicate_uri_slugifies_verb():
    assert str(T._predicate_uri("signed a deed")) == str(FICHERO) + "signed-a-deed"


def test_predicate_uri_empty_verb_is_asserted_about():
    assert str(T._predicate_uri("")) == str(FICHERO) + "assertedAbout"


# ===========================================================================
# claim_to_triples — structured SVO
# ===========================================================================


def test_claim_structured_resolves_object_to_entity():
    g = T.make_graph()
    subj = _entity(id="e1", canonical_name="Pérez", entity_type=EntityType.person)
    obj = _entity(id="e2", canonical_name="the deed", entity_type=EntityType.other)
    claim = _claim(id="c1", entity_ids=["e1"], metadata={"verb": "signed", "object": "the deed"})
    T.claim_to_triples(g, claim, {"e1": subj, "e2": obj})

    pred = T._predicate_uri("signed")
    # Object string matched a known entity -> resource-to-resource edge.
    assert (T._entity_uri("e1"), pred, T._entity_uri("e2")) in g
    # Reified statement carries claim-level metadata.
    curi = T._claim_uri("c1")
    assert (curi, RDF.type, RDF.Statement) in g
    assert (curi, FICHERO.sourceDocument, T._doc_uri("d1")) in g
    assert (curi, RDF.subject, T._entity_uri("e1")) in g
    assert (curi, RDF.object, Literal("the deed")) in g


def test_claim_structured_falls_back_to_literal_object():
    g = T.make_graph()
    subj = _entity(id="e1", canonical_name="Pérez")
    claim = _claim(id="c1", entity_ids=["e1"], metadata={"verb": "liked", "object": "coffee"})
    T.claim_to_triples(g, claim, {"e1": subj})  # 'coffee' matches no entity
    assert (T._entity_uri("e1"), T._predicate_uri("liked"), Literal("coffee")) in g


def test_claim_resolves_object_via_alias():
    g = T.make_graph()
    subj = _entity(id="e1", canonical_name="Pérez")
    obj = _entity(id="e2", canonical_name="Escritura", aliases=["the deed"])
    claim = _claim(id="c1", entity_ids=["e1"], metadata={"verb": "signed", "object": "the deed"})
    T.claim_to_triples(g, claim, {"e1": subj, "e2": obj})
    assert (T._entity_uri("e1"), T._predicate_uri("signed"), T._entity_uri("e2")) in g


def test_claim_metadata_fields_emitted():
    g = T.make_graph()
    claim = _claim(id="c1", entity_ids=["e1"], metadata={"verb": "v", "object": "o"},
                   epistemic_status="confirmed", source_page_label="p. 3",
                   source_excerpt="…text…", confidence=0.9)
    T.claim_to_triples(g, claim, {})
    curi = T._claim_uri("c1")
    assert (curi, FICHERO.epistemicStatus, Literal("confirmed")) in g
    assert (curi, FICHERO.sourcePageLabel, Literal("p. 3")) in g
    assert (curi, FICHERO.sourceExcerpt, Literal("…text…")) in g
    assert len(list(g.triples((curi, FICHERO.confidence, None)))) == 1


# ===========================================================================
# claim_to_triples — unstructured
# ===========================================================================


def test_claim_unstructured_emits_document_about_edge():
    g = T.make_graph()
    claim = _claim(id="c1", entity_ids=["e1"])  # no verb/object metadata
    T.claim_to_triples(g, claim)
    # No SVO -> document mention edge instead of a predicate edge.
    assert (T._doc_uri("d1"), SCHEMA.about, T._entity_uri("e1")) in g
    assert (T._claim_uri("c1"), RDF.type, RDF.Statement) in g


def test_claim_multiple_entities_each_get_edge():
    g = T.make_graph()
    claim = _claim(id="c1", entity_ids=["e1", "e2"])
    T.claim_to_triples(g, claim)
    assert (T._doc_uri("d1"), SCHEMA.about, T._entity_uri("e1")) in g
    assert (T._doc_uri("d1"), SCHEMA.about, T._entity_uri("e2")) in g


# ===========================================================================
# build_graph / persist / sparql
# ===========================================================================


def test_build_graph_combines_entities_and_claims():
    subj = _entity(id="e1", canonical_name="Pérez", entity_type=EntityType.person)
    obj = _entity(id="e2", canonical_name="the deed", entity_type=EntityType.other)
    claim = _claim(id="c1", entity_ids=["e1"], metadata={"verb": "signed", "object": "the deed"})
    g = T.build_graph([subj, obj], [claim])
    # entity_index built internally -> object resolves to the entity URI.
    assert (T._entity_uri("e1"), T._predicate_uri("signed"), T._entity_uri("e2")) in g


def test_persist_roundtrips_ntriples(tmp_path):
    g = T.build_graph([_entity(id="e1", canonical_name="Pérez")], [])
    out = tmp_path / "sub" / "graph.nt"  # parent dir does not exist yet
    T.persist(g, out)
    assert out.exists() and out.stat().st_size > 0
    reparsed = Graph()
    reparsed.parse(str(out), format="nt")
    assert len(reparsed) == len(g)


def test_persist_turtle_format(tmp_path):
    g = T.build_graph([_entity(id="e1", canonical_name="Pérez")], [])
    out = tmp_path / "graph.ttl"
    T.persist(g, out, format="turtle")
    assert out.exists() and out.read_text(encoding="utf-8").strip()


def test_sparql_query_returns_rows():
    g = T.build_graph([_entity(id="e1", canonical_name="Pérez", entity_type=EntityType.person)], [])
    rows = T.sparql(g, "SELECT ?p WHERE { ?p a <http://xmlns.com/foaf/0.1/Person> }")
    assert len(rows) == 1
    empty = T.sparql(g, "SELECT ?p WHERE { ?p a <https://schema.org/Event> }")
    assert list(empty) == []
