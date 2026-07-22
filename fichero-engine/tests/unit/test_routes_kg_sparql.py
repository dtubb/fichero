"""Tests for POST /api/kg/sparql (#987 / #983 Stage 1c).

The endpoint is a thin wrapper over fichero.kg.triples.sparql() —
materializes the RDF graph from current entity + claim rows and runs
the user's SPARQL query against it. Read-only; mutating verbs rejected.
"""

import asyncio

import pytest
from fastapi import HTTPException

from fichero.models.knowledge import (
    ClaimCurationState,
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)


SPARQL_URL = "/api/kg/sparql"
SPARQL_QUERY_URL = "/api/kg/query/sparql"
SPARQL_EXAMPLES_URL = "/api/kg/query/examples"
RDF_EXPORT_URL = "/api/kg/export/rdf"


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
    def test_rdf_cache_is_bounded(self):
        from fichero.api.routes import kg_sparql

        cache = kg_sparql._RDF_CACHE
        cache.clear()
        cache.update({str(index): ((index,), object()) for index in range(8)})
        cache.pop(next(iter(cache)))
        cache["new"] = ((9,), object())
        assert len(cache) == kg_sparql._RDF_CACHE_MAX_ENTRIES

    def test_query_timeout_returns_408(self, db, monkeypatch):
        from fichero.api.routes import kg_sparql

        async def timeout(*_args, **_kwargs):
            raise TimeoutError

        monkeypatch.setattr(kg_sparql.asyncio, "wait_for", timeout)
        monkeypatch.setattr(kg_sparql.asyncio, "to_thread", lambda *_args: None)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(kg_sparql.sparql_query(kg_sparql.SparqlRequest(query="ASK {}"), db))

        assert exc.value.status_code == 408

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

    def test_canonical_query_route_returns_expected_bindings(self, client, db):
        alice = _make_person("e-a-bindings", "Alice")
        bob = _make_person("e-b-bindings", "Bob")
        claim = _make_svo_claim(
            "claim-binds",
            "Alice",
            "visited",
            "Bob",
            [alice.id, bob.id],
        )
        db.save(alice)
        db.save(bob)
        db.save(claim)

        r = client.post(
            SPARQL_QUERY_URL,
            json={
                "query": (
                    "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
                    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
                    "SELECT ?subjectLabel WHERE { "
                    "?claim rdf:subject ?subject . "
                    "?subject rdfs:label ?subjectLabel . "
                    "} ORDER BY ?subjectLabel"
                )
            },
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["row_count"] >= 1
        labels = [row["bindings"]["subjectLabel"] for row in payload["rows"]]
        assert "Alice" in labels
        assert "Bob" in labels

    def test_empty_query_returns_clean_400(self, client):
        r = client.post(SPARQL_QUERY_URL, json={"query": ""})

        assert r.status_code == 400
        assert "SPARQL error" in r.json()["detail"]

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

    def test_canonical_query_route_matches_legacy_route(self, client, db):
        db.save(_make_person("e-a", "Alice"))

        payload = {
            "query": (
                "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> "
                "SELECT ?label WHERE { ?s rdfs:label ?label } "
                "ORDER BY ?label"
            ),
        }

        legacy = client.post(SPARQL_URL, json=payload)
        canonical = client.post(SPARQL_QUERY_URL, json=payload)

        assert legacy.status_code == 200
        assert canonical.status_code == 200
        assert canonical.json()["rows"] == legacy.json()["rows"]

    def test_examples_endpoint_lists_seed_queries(self, client):
        r = client.get(SPARQL_EXAMPLES_URL)

        assert r.status_code == 200
        data = r.json()
        assert len(data["examples"]) >= 2
        example_ids = [example["id"] for example in data["examples"]]
        assert "people-labels" in example_ids
        assert "claims-with-source" in example_ids
        people_labels = next(
            example for example in data["examples"] if example["id"] == "people-labels"
        )
        assert "title" in people_labels
        assert "query" in people_labels
        assert "SELECT" in people_labels["query"]

    def test_rdf_export_returns_serialized_graph(self, client, db):
        db.save(_make_person("e-a", "Alice"))

        r = client.get(f"{RDF_EXPORT_URL}?format=turtle")

        assert r.status_code == 200
        assert "text/turtle" in r.headers["content-type"]
        assert r.headers["content-disposition"].endswith('knowledge-graph.ttl"')
        assert "Alice" in r.text

    def test_rdf_export_empty_graph_returns_valid_empty_serialization(self, client):
        r = client.get(f"{RDF_EXPORT_URL}?format=nt")

        assert r.status_code == 200
        assert "application/n-triples" in r.headers["content-type"]
        assert r.headers["content-disposition"].endswith('knowledge-graph.nt"')
        assert r.text.strip() == ""
