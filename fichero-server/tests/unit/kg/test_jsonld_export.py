"""Coverage for `GET /api/kg/export/rdf` (#4753 / #4754).

The route already existed and already produced JSON-LD before this change
-- the two issues' premise ("no JSON-LD export exists") was wrong. What was
actually missing, and what this file pins:

- `format=json-ld` used rdflib's auto-generated @context (whatever prefixes
  happened to be bound on the graph) rather than a real, documented,
  selectable context. #4753 makes that context an explicit, named profile
  (`knowledge.jsonld_context.JSONLD_CONTEXTS`).
- The export was never validated before being returned -- a malformed
  graph would have shipped silently. #4754 adds a round-trip parse that
  raises rather than serving a half-file.
- The route (all four formats) had almost no test coverage: `turtle`/`nt`
  had one smoke test each in `test_routes_kg_sparql.py`; `json-ld`/`xml`
  had none.

Retag for `docs/contributor_manual/specs/kg/kg-enrichment.md` (docs lane
applies -- engine lane does not edit specs): `kg.jsonld.export` was
[MISSING] per the issue; the honest status is the export existed and now
has a curated, selectable context ([OK], not [MISSING] -- the issue's
"no JSON-LD" premise was wrong, only "no curated context" was right).
`kg.jsonld.export.validated` was [MISSING] and is now [OK] for
expand/compact round-trip; SHACL/ShEx remains [MISSING] (no shape is
declared for the KG yet, spec's own open question).
"""

from __future__ import annotations

import pytest
from rdflib import Graph
from rdflib.compare import isomorphic

from fichero_server.knowledge.jsonld_context import JSONLD_CONTEXTS
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)

RDF_EXPORT_URL = "/api/kg/export/rdf"


def _make_person(eid: str, name: str) -> KnowledgeEntity:
    return KnowledgeEntity(id=eid, canonical_name=name, entity_type=EntityType.person)


def _make_svo_claim(cid: str, subject: str, verb: str, obj: str, entity_ids: list[str]) -> KnowledgeClaim:
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


def _seed_entity_and_claim(db):
    alice = _make_person("e-alice", "Alice")
    bob = _make_person("e-bob", "Bob")
    claim = _make_svo_claim("claim-1", "Alice", "visited", "Bob", [alice.id, bob.id])
    db.save(alice)
    db.save(bob)
    db.save(claim)


# =============================================================================
# #4753 — export entities + claims as JSON-LD with a real, curated context
# =============================================================================


def test_export_entities_claims_as_jsonld_with_context(client, db):
    _seed_entity_and_claim(db)

    r = client.get(f"{RDF_EXPORT_URL}?format=json-ld")

    assert r.status_code == 200
    assert "application/ld+json" in r.headers["content-type"]
    assert r.headers["content-disposition"].endswith('knowledge-graph.jsonld"')
    payload = r.json()
    assert payload != []
    # The context is our real, named schema-org profile -- not rdflib's
    # auto-generated one -- so it must contain the documented prefixes.
    doc = payload[0] if isinstance(payload, list) else payload
    context = doc.get("@context", {})
    assert context.get("foaf") == "http://xmlns.com/foaf/0.1/"
    assert context.get("schema") == str(_schema_iri())
    # The exported label survives compaction.
    names = _flatten_field(payload, "rdfs:label") or _flatten_field(payload, "http://www.w3.org/2000/01/rdf-schema#label")
    assert any("Alice" in str(n) for n in names) or "Alice" in r.text


def _schema_iri():
    from fichero_server.knowledge.triples import SCHEMA

    return SCHEMA


def _flatten_field(payload, key):
    docs = payload if isinstance(payload, list) else [payload]
    values = []
    for doc in docs:
        v = doc.get(key)
        if v is None:
            continue
        if isinstance(v, list):
            for item in v:
                values.append(item.get("@value", item) if isinstance(item, dict) else item)
        else:
            values.append(v)
    return values


def test_jsonld_context_is_selectable_and_named(client, db):
    """The kg-enrichment ruling is "@context: selectable too" -- prove the
    `context` query param actually changes the emitted context, not a
    no-op. Only 'schema-org' ships; an unknown profile is rejected."""
    db.save(_make_person("e-solo", "Solo"))

    ok = client.get(f"{RDF_EXPORT_URL}?format=json-ld&context=schema-org")
    assert ok.status_code == 200
    doc = ok.json()[0] if isinstance(ok.json(), list) else ok.json()
    assert doc["@context"] == JSONLD_CONTEXTS["schema-org"]

    unknown = client.get(f"{RDF_EXPORT_URL}?format=json-ld&context=linked-art")
    assert unknown.status_code == 422  # not stubbed -- rejected, not a silent fallback


def test_jsonld_export_empty_graph_is_valid(client):
    r = client.get(f"{RDF_EXPORT_URL}?format=json-ld")

    assert r.status_code == 200
    assert "application/ld+json" in r.headers["content-type"]
    # With an explicit @context, rdflib emits {"@context": ..., "@graph": []}
    # for an empty graph -- still valid, still round-trips to zero triples.
    body = r.json()
    assert body["@graph"] == []
    reparsed = Graph()
    reparsed.parse(data=r.content, format="json-ld")
    assert len(reparsed) == 0


# =============================================================================
# #4754 — the export is validated before being handed over; malformed never
# ships (prefer-raise, never a silent half-file).
# =============================================================================


def test_malformed_export_raises_never_ships(client, db, monkeypatch):
    from fichero_server.api.routes.kg import sparql as kg_sparql

    _seed_entity_and_claim(db)

    class _BrokenGraph:
        """Stands in for `_cached_rdf_graph`'s return value: serializes to
        text that is NOT valid JSON-LD, simulating a corrupted context
        mapping -- the exact failure #4754 must catch before it ships."""

        def serialize(self, *, format, context=None, encoding="utf-8"):
            if format == "json-ld":
                return b"{not: valid, json-ld"
            raise AssertionError("only json-ld is exercised by this test")

    monkeypatch.setattr(kg_sparql, "_cached_rdf_graph", lambda _db: _BrokenGraph())

    r = client.get(f"{RDF_EXPORT_URL}?format=json-ld")

    assert r.status_code == 500
    assert "validation" in r.json()["detail"].lower()


def test_validate_jsonld_export_raises_http_exception_directly():
    """Unit-level check on the validator itself, bypassing the route."""
    from fastapi import HTTPException

    from fichero_server.api.routes.kg.sparql import _validate_jsonld_export

    try:
        _validate_jsonld_export(b"{not valid json-ld at all", "schema-org")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 500


# =============================================================================
# Team-lead review follow-up: the other three formats (nt/turtle/xml) had
# near-zero coverage on this route -- pin serialize -> parse -> same triple
# count for each, riding the same seeded graph.
# =============================================================================


@pytest.mark.parametrize("fmt,rdflib_format", [
    ("nt", "nt"),
    ("turtle", "turtle"),
    ("xml", "xml"),
])
def test_export_round_trips_for_every_non_jsonld_format(client, db, fmt, rdflib_format):
    _seed_entity_and_claim(db)

    r = client.get(f"{RDF_EXPORT_URL}?format={fmt}")
    assert r.status_code == 200

    reparsed = Graph()
    reparsed.parse(data=r.content, format=rdflib_format)
    assert len(reparsed) > 0

    # Same triple count as the graph the route actually served from.
    from fichero_server.api.routes.kg.sparql import _cached_rdf_graph

    live = _cached_rdf_graph(db)
    assert len(reparsed) == len(live)


def test_jsonld_export_round_trips_to_isomorphic_graph(client, db):
    """Graph-level round trip: serialize -> parse -> isomorphic to the
    live graph. Note on scope for #4756 (export -> import -> export
    stability): this proves the SERIALIZE side of that invariant --
    reparsing our own JSON-LD reconstructs the same graph structurally.
    It does NOT cover #4756 itself, which needs a real Fichero-side
    IMPORTER (#4755, not built) to map external JSON-LD back onto
    KnowledgeEntity/KnowledgeClaim rows -- that mapping step, and the
    second export after re-import, are untested by this file."""
    from fichero_server.api.routes.kg.sparql import _cached_rdf_graph

    _seed_entity_and_claim(db)

    r = client.get(f"{RDF_EXPORT_URL}?format=json-ld")
    assert r.status_code == 200

    reparsed = Graph()
    reparsed.parse(data=r.content, format="json-ld")

    live = _cached_rdf_graph(db)
    assert isomorphic(reparsed, live)
