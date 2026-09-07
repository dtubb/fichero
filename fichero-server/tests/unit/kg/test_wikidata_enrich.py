"""Wikidata enrichment fetch + adapt service (offline; HTTP is stubbed)."""

import pytest

from fichero_server.knowledge import wikidata_enrich as we


# --- SPARQL-results-JSON shape, as query.wikidata.org returns it ------------

_SPARQL_PAYLOAD = {
    "head": {"vars": ["prop", "propLabel", "value", "valueLabel"]},
    "results": {
        "bindings": [
            {
                "prop": {"type": "uri", "value": "http://www.wikidata.org/entity/P569"},
                "propLabel": {"type": "literal", "value": "date of birth"},
                "value": {"type": "literal", "value": "1952-03-11T00:00:00Z"},
                "valueLabel": {"type": "literal", "value": "1952-03-11T00:00:00Z"},
            },
            {
                "prop": {"type": "uri", "value": "http://www.wikidata.org/entity/P19"},
                "propLabel": {"type": "literal", "value": "place of birth"},
                "value": {"type": "uri", "value": "http://www.wikidata.org/entity/Q350"},
                "valueLabel": {"type": "literal", "value": "Cambridge"},
            },
            # Duplicate row (Wikidata returns repeats for multi-valued refs) —
            # must be collapsed by statement_id.
            {
                "prop": {"type": "uri", "value": "http://www.wikidata.org/entity/P19"},
                "propLabel": {"type": "literal", "value": "place of birth"},
                "value": {"type": "uri", "value": "http://www.wikidata.org/entity/Q350"},
                "valueLabel": {"type": "literal", "value": "Cambridge"},
            },
        ]
    },
}


def test_parse_sparql_statements_adapts_literals_and_entities():
    statements = we.parse_sparql_statements(_SPARQL_PAYLOAD)
    assert len(statements) == 2  # duplicate collapsed

    birth = next(s for s in statements if s.property_id == "P569")
    assert birth.property_label == "date of birth"
    assert birth.value_label == "1952-03-11T00:00:00Z"
    assert birth.value_qid is None

    place = next(s for s in statements if s.property_id == "P19")
    assert place.value_qid == "Q350"
    assert place.value_url == "http://www.wikidata.org/entity/Q350"
    assert place.value_label == "Cambridge"


def test_parse_sparql_skips_non_property_predicates():
    payload = {
        "results": {
            "bindings": [
                {
                    "prop": {"type": "uri", "value": "http://www.wikidata.org/entity/Q5"},
                    "value": {"type": "literal", "value": "noise"},
                }
            ]
        }
    }
    assert we.parse_sparql_statements(payload) == []


def test_build_statements_query_validates_qid():
    query = we.build_statements_query("Q42")
    assert "wd:Q42" in query
    assert "wikibase:label" in query
    with pytest.raises(ValueError):
        we.build_statements_query("not-a-qid")


def test_require_qid_strips_entity_uri():
    assert we._require_qid("http://www.wikidata.org/entity/Q42") == "Q42"
    assert we._require_qid("  Q7 ") == "Q7"


def test_statement_to_claim_text():
    stmt = we.WikidataStatement(
        property_id="P106", property_label="occupation", value_label="writer"
    )
    assert (
        we.statement_to_claim_text("Douglas Adams", stmt)
        == "Douglas Adams — occupation: writer"
    )


# --- stubbed fetch ----------------------------------------------------------


class _Response:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, url, params=None, headers=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._response


@pytest.mark.asyncio
async def test_fetch_statements_sparql_uses_endpoint_and_parses():
    client = _Client(_Response(payload=_SPARQL_PAYLOAD))
    statements = await we.fetch_statements_sparql(
        "Q42", "https://example.org/sparql", client_factory=lambda: client
    )
    assert {s.property_id for s in statements} == {"P569", "P19"}
    assert client.calls[0]["url"] == "https://example.org/sparql"
    assert client.calls[0]["params"]["format"] == "json"
    assert "wd:Q42" in client.calls[0]["params"]["query"]


# --- JSON-LD path via vendored rdflib --------------------------------------

_JSONLD = {
    "@graph": [
        {
            "@id": "http://www.wikidata.org/entity/Q42",
            "http://www.wikidata.org/prop/direct/P106": {
                "@id": "http://www.wikidata.org/entity/Q36180"
            },
        },
        {
            "@id": "http://www.wikidata.org/entity/Q36180",
            "http://www.w3.org/2000/01/rdf-schema#label": {
                "@value": "writer",
                "@language": "en",
            },
        },
    ]
}


def test_parse_jsonld_statements_uses_rdflib_and_resolves_labels():
    statements = we.parse_jsonld_statements(_JSONLD, "Q42")
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt.property_id == "P106"
    assert stmt.property_label == "occupation"  # curated fallback
    assert stmt.value_qid == "Q36180"
    assert stmt.value_label == "writer"
