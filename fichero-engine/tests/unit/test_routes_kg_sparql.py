"""Tests for POST /api/kg/sparql (#987 / #983 Stage 1c).

The endpoint is a thin wrapper over fichero.kg.triples.sparql() —
materializes the RDF graph from current entity + claim rows and runs
the user's SPARQL query against it. Read-only; mutating verbs rejected.
"""

import pytest

from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)


SPARQL_URL = "/api/kg/sparql"


def _make_person(eid: str, name: str) -> KnowledgeEntity:
    return KnowledgeEntity(id=eid, canonical_name=name, entity_type=EntityType.person)


def _make_svo_claim(
    cid: str,
    subject: str,
    verb: str,
    obj: str,
    entity_ids: list[str],
) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=cid,
        text=f"{subject} {verb} {obj}.",
        source_document_id="doc-1",
        source_ids=["doc-1"],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.confirmed,
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.8,
        entity_ids=entity_ids,
        metadata={"subject": subject, "verb": verb, "object": obj},
    )


class TestSparqlSafety:
    """Mutating SPARQL verbs are rejected."""

    @pytest.mark.parametrize("verb", [
        "INSERT DATA { <a> <b> <c> }",
        "DELETE WHERE { ?s ?p ?o }",
        "DROP GRAPH <g>",
        "CLEAR DEFAULT",
        "LOAD <http://example/data>",
        "CREATE GRAPH <g>",
    ])
    def test_mutating_verb_returns_400(self, client, verb):
        r = client.post(SPARQL_URL, json={"query": verb})
        assert r.status_code == 400
        assert "Mutating" in r.json()["detail"]


class TestSparqlReadOnly:
    def test_select_on_empty_graph_returns_empty(self, client):
        r = client.post(SPARQL_URL, json={
            "query": "SELECT ?s WHERE { ?s ?p ?o }",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["rows"] == []
        assert data["row_count"] == 0
        assert data["truncated"] is False

    def test_ask_runs(self, client, db):
        db.save(_make_person("e-a", "Alice"))
        r = client.post(SPARQL_URL, json={
            "query": (
                "PREFIX foaf: <http://xmlns.com/foaf/0.1/> "
                "ASK { ?p a foaf:Person }"
            ),
        })
        assert r.status_code == 200
        data = r.json()
        # ASK returns one row with a single boolean binding
        assert data["row_count"] == 1

    def test_select_returns_entity_label(self, client, db):
        db.save(_make_person("e-a", "Alice"))
        db.save(_make_person("e-b", "Bob"))
        r = client.post(SPARQL_URL, json={
            "query": (
                "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
                "SELECT ?label WHERE { ?s rdfs:label ?label } "
                "ORDER BY ?label"
            ),
        })
        assert r.status_code == 200
        data = r.json()
        labels = [row["bindings"]["label"] for row in data["rows"]]
        assert "Alice" in labels
        assert "Bob" in labels

    def test_limit_caps_rows(self, client, db):
        for idx in range(5):
            db.save(_make_person(f"e-{idx}", f"Person {idx}"))
        r = client.post(SPARQL_URL, json={
            "query": (
                "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
                "SELECT ?s ?label WHERE { ?s rdfs:label ?label }"
            ),
            "limit": 2,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["row_count"] == 2
        assert data["truncated"] is True

    def test_malformed_query_returns_400(self, client):
        r = client.post(SPARQL_URL, json={
            "query": "SELECT WHERE { this is not valid sparql",
        })
        assert r.status_code == 400
        assert "SPARQL error" in r.json()["detail"]
