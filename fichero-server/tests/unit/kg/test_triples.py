"""Tests for the RDF triple substrate (#899 Phase A).

Locks the contract that:
- Each EntityType maps to the right ontology class (FOAF.Person,
  schema:Place, etc.).
- KnowledgeClaim with SVO metadata emits a subject-predicate-object
  edge per linked entity.
- Reification carries epistemic_status, claim_type, source provenance.
- SPARQL queries return what the DuckDB rows would return.
"""

from __future__ import annotations

from rdflib import Literal
from rdflib.namespace import FOAF, RDF, RDFS, SKOS

from fichero_server.models.knowledge import (
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.kg import triples


# =============================================================================
# Entity → triples
# =============================================================================


class TestEntityToTriples:
    def test_person_maps_to_foaf_person(self):
        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-1",
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
        )
        triples.entity_to_triples(g, ent)
        e_uri = triples._entity_uri("e-1")
        assert (e_uri, RDF.type, FOAF.Person) in g
        assert (e_uri, RDFS.label, Literal("Eugenio Córdoba")) in g

    def test_place_maps_to_schema_place(self):
        from fichero_server.kg.triples import SCHEMA

        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-2",
            canonical_name="Chocó",
            entity_type=EntityType.location,
        )
        triples.entity_to_triples(g, ent)
        assert (triples._entity_uri("e-2"), RDF.type, SCHEMA.Place) in g

    def test_concept_maps_to_skos_concept(self):
        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-3",
            canonical_name="economic exclusion",
            entity_type=EntityType.concept,
        )
        triples.entity_to_triples(g, ent)
        assert (triples._entity_uri("e-3"), RDF.type, SKOS.Concept) in g

    def test_aliases_become_skos_altlabel(self):
        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-4",
            canonical_name="Davidson",
            entity_type=EntityType.person,
            aliases=["Deibinson", "Deibi"],
        )
        triples.entity_to_triples(g, ent)
        e_uri = triples._entity_uri("e-4")
        assert (e_uri, SKOS.altLabel, Literal("Deibinson")) in g
        assert (e_uri, SKOS.altLabel, Literal("Deibi")) in g

    def test_description_becomes_rdfs_comment(self):
        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-5",
            canonical_name="Juan Pérez",
            entity_type=EntityType.person,
            description="signed the deed in the 1930 sale",
        )
        triples.entity_to_triples(g, ent)
        assert (
            triples._entity_uri("e-5"),
            RDFS.comment,
            Literal("signed the deed in the 1930 sale"),
        ) in g

    def test_language_tag_on_label(self):
        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-6",
            canonical_name="Chocó",
            entity_type=EntityType.location,
            language="es",
        )
        triples.entity_to_triples(g, ent)
        e_uri = triples._entity_uri("e-6")
        assert (e_uri, RDFS.label, Literal("Chocó", lang="es")) in g


# =============================================================================
# Claim → triples
# =============================================================================


class TestClaimToTriples:
    def test_svo_produces_subject_predicate_object_edge(self):
        from fichero_server.kg.triples import FICHERO

        g = triples.make_graph()
        ent = KnowledgeEntity(
            id="e-1",
            canonical_name="Juan Pérez",
            entity_type=EntityType.person,
        )
        triples.entity_to_triples(g, ent)
        claim = KnowledgeClaim(
            text="Juan Pérez signed the deed.",
            source_document_id="doc-1",
            entity_ids=["e-1"],
            metadata={"verb": "signed", "object": "the deed"},
        )
        triples.claim_to_triples(g, claim)
        # Predicate URI is slugified from the verb.
        signed = FICHERO["signed"]
        assert (triples._entity_uri("e-1"), signed, Literal("the deed")) in g

    def test_reification_carries_claim_level_metadata(self):
        from fichero_server.kg.triples import FICHERO

        g = triples.make_graph()
        claim = KnowledgeClaim(
            id="c-1",
            text="Pérez signed the deed.",
            source_document_id="doc-1",
            source_page_label="Page 14",
            source_excerpt="Pérez signed the deed in 1933.",
            entity_ids=["e-1"],
            epistemic_status=EpistemicStatus.confirmed,
            claim_type=ClaimType.fact,
            confidence=0.9,
            metadata={"verb": "signed", "object": "the deed"},
        )
        triples.claim_to_triples(g, claim)
        c_uri = triples._claim_uri("c-1")
        assert (c_uri, RDF.type, RDF.Statement) in g
        assert (c_uri, FICHERO.epistemicStatus, Literal("confirmed")) in g
        assert (c_uri, FICHERO.claimType, Literal("fact")) in g
        assert (c_uri, FICHERO.sourcePageLabel, Literal("Page 14")) in g
        assert (
            c_uri,
            FICHERO.sourceExcerpt,
            Literal("Pérez signed the deed in 1933."),
        ) in g

    def test_no_svo_emits_schema_about_edge(self):
        from fichero_server.kg.triples import SCHEMA

        g = triples.make_graph()
        claim = KnowledgeClaim(
            text="Juan is mentioned.",
            source_document_id="doc-1",
            entity_ids=["e-1"],
            # No verb/object — falls back to schema:about
            metadata={},
        )
        triples.claim_to_triples(g, claim)
        doc_uri = triples._doc_uri("doc-1")
        ent_uri = triples._entity_uri("e-1")
        assert (doc_uri, SCHEMA.about, ent_uri) in g

    def test_object_resolves_to_entity_when_known(self):
        from fichero_server.kg.triples import FICHERO

        g = triples.make_graph()
        subject = KnowledgeEntity(
            id="e-1", canonical_name="Juan", entity_type=EntityType.person
        )
        target = KnowledgeEntity(
            id="e-2", canonical_name="The Deed", entity_type=EntityType.other
        )
        triples.entity_to_triples(g, subject)
        triples.entity_to_triples(g, target)
        claim = KnowledgeClaim(
            text="Juan signed The Deed.",
            source_document_id="doc-1",
            entity_ids=["e-1"],
            metadata={"verb": "signed", "object": "The Deed"},
        )
        triples.claim_to_triples(
            g, claim, entities={"e-1": subject, "e-2": target}
        )
        # Object resolved to the entity URI rather than a literal.
        signed = FICHERO["signed"]
        assert (triples._entity_uri("e-1"), signed, triples._entity_uri("e-2")) in g


# =============================================================================
# SPARQL roundtrip
# =============================================================================


class TestSparqlRoundtrip:
    def test_sparql_finds_person_by_label(self):
        entities = [
            KnowledgeEntity(
                id="e-1",
                canonical_name="Davidson",
                entity_type=EntityType.person,
                aliases=["Deibinson"],
            ),
            KnowledgeEntity(
                id="e-2",
                canonical_name="Eugenio Córdoba",
                entity_type=EntityType.person,
            ),
        ]
        g = triples.build_graph(entities, claims=[])
        rows = triples.sparql(
            g,
            """
            PREFIX foaf: <http://xmlns.com/foaf/0.1/>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?label WHERE {
              ?p a foaf:Person ; rdfs:label ?label .
              FILTER(CONTAINS(LCASE(STR(?label)), "davidson"))
            }
            """,
        )
        labels = [str(row[0]) for row in rows]
        assert "Davidson" in labels

    def test_sparql_finds_claims_by_epistemic_status(self):
        ent = KnowledgeEntity(
            id="e-1", canonical_name="Pérez", entity_type=EntityType.person
        )
        confirmed = KnowledgeClaim(
            text="Pérez signed.",
            source_document_id="doc-1",
            entity_ids=["e-1"],
            epistemic_status=EpistemicStatus.confirmed,
            metadata={"verb": "signed", "object": "the deed"},
        )
        tentative = KnowledgeClaim(
            text="Pérez may have signed.",
            source_document_id="doc-1",
            entity_ids=["e-1"],
            epistemic_status=EpistemicStatus.tentative,
            metadata={"verb": "may have signed", "object": "the deed"},
        )
        g = triples.build_graph([ent], [confirmed, tentative])
        rows = triples.sparql(
            g,
            """
            PREFIX fichero: <https://fichero.app/ns#>
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            SELECT ?s WHERE {
              ?s a rdf:Statement ; fichero:epistemicStatus "confirmed" .
            }
            """,
        )
        assert len(rows) == 1


# =============================================================================
# Persistence
# =============================================================================


class TestPersist:
    def test_ntriples_roundtrip(self, tmp_path):
        ent = KnowledgeEntity(
            id="e-1",
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
        )
        g = triples.build_graph([ent], claims=[])

        out = tmp_path / "kg.nt"
        triples.persist(g, out, format="nt")
        assert out.exists()
        # File should contain the canonical_name as a literal.
        text = out.read_text(encoding="utf-8")
        assert "Eugenio C" in text  # accent encoded

    def test_persist_emits_no_encoding_warning(self, tmp_path):
        """rdflib's NTSerializer warns "always uses UTF-8 encoding. Given
        encoding was: None" when persist() doesn't pass an explicit
        encoding. Treat that warning as a failure. (#1026)"""
        import warnings

        ent = KnowledgeEntity(
            id="e-1",
            canonical_name="Eugenio Córdoba",
            entity_type=EntityType.person,
        )
        g = triples.build_graph([ent], claims=[])
        out = tmp_path / "kg.nt"
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            triples.persist(g, out, format="nt")
        assert out.exists()
