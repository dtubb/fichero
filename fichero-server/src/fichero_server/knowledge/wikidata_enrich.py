"""Fetch + adapt a Wikidata entity's statements into importable Fichero claims.

This is the engine half of the "Enrich from Wikidata" feature. It builds ON the
existing authority-link seam (``AuthoritySnapshot`` / ``entity.metadata
["authority_links"]`` in ``api.routes.kg.entity_curation``): once an entity is
linked to a Wikidata QID, this module fetches that QID's *statements* and adapts
them into ``WikidataStatement`` rows the review-and-import panel lists.

Provenance is load-bearing honesty (see the route's importer): the resulting
claims are marked WIKIDATA-SOURCED, never given a ``source_document_id``. A
Wikidata statement is an *external assertion*, not something read in this corpus.

Two fetch paths, both offline-testable by stubbing the HTTP GET:

* SPARQL (default) — a SELECT against the configured endpoint
  (``https://query.wikidata.org/sparql`` by default). The ``wikibase:label``
  service resolves property + value labels server-side, so the P-number →
  human-label mapping (P569 → "date of birth", …) is complete, not a hardcoded
  subset.
* JSON-LD — ``Special:EntityData/<QID>.jsonld`` parsed with the vendored
  ``rdflib``. Endpoint-independent fallback; labels come from the curated
  ``WIKIDATA_PROPERTY_LABELS`` map plus any ``rdfs:label`` present in the graph.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

DEFAULT_WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
_WIKIDATA_ENTITY_PREFIX = "http://www.wikidata.org/entity/"
_WIKIDATA_PROP_DIRECT = "http://www.wikidata.org/prop/direct/"
_USER_AGENT = "Fichero/wikidata-enrich (https://tubb.ca/apps/fichero)"

# Curated labels for the common biographical properties named in the design.
# Used only as a fallback for the JSON-LD path (the SPARQL label service
# supplies labels for *every* property, curated or not).
WIKIDATA_PROPERTY_LABELS: dict[str, str] = {
    "P569": "date of birth",
    "P570": "date of death",
    "P19": "place of birth",
    "P20": "place of death",
    "P106": "occupation",
    "P27": "country of citizenship",
    "P39": "position held",
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
    "P69": "educated at",
    "P108": "employer",
    "P937": "work location",
    "P103": "native language",
    "P1412": "languages spoken, written or signed",
}


class WikidataStatement(BaseModel):
    """One adapted Wikidata statement, ready for review + import as a claim."""

    property_id: str = Field(description="Wikidata property id, e.g. 'P569'.")
    property_label: str = Field(description="Human label, e.g. 'date of birth'.")
    value_label: str = Field(description="Human-readable value, e.g. '1952-03-11'.")
    value_qid: str | None = Field(
        default=None,
        description="Wikidata QID when the value is itself an entity, else null.",
    )
    value_url: str | None = Field(
        default=None, description="Source URL for an entity-valued statement."
    )

    @property
    def statement_id(self) -> str:
        """Stable id for de-dup + checkbox selection in the panel."""
        return f"{self.property_id}:{self.value_qid or self.value_label}"


def build_statements_query(qid: str, lang: str = "en") -> str:
    """SPARQL SELECT for a QID's truthy statements with server-resolved labels."""
    safe_qid = _require_qid(qid)
    safe_lang = "".join(c for c in lang if c.isalnum() or c in "-,") or "en"
    return (
        "SELECT ?prop ?propLabel ?value ?valueLabel WHERE {\n"
        f"  wd:{safe_qid} ?p ?value .\n"
        "  ?prop wikibase:directClaim ?p .\n"
        "  SERVICE wikibase:label { bd:serviceParam wikibase:language "
        f'"{safe_lang},mul,en". }}\n'
        "}\nORDER BY ?propLabel"
    )


def _require_qid(qid: str) -> str:
    """Validate the QID shape so it is safe to interpolate into a query/URL."""
    cleaned = (qid or "").strip()
    if cleaned.startswith(_WIKIDATA_ENTITY_PREFIX):
        cleaned = cleaned[len(_WIKIDATA_ENTITY_PREFIX) :]
    if not (cleaned.startswith("Q") and cleaned[1:].isdigit()):
        raise ValueError(f"Not a Wikidata entity id (expected 'Q…'): {qid!r}")
    return cleaned


def _qid_from_uri(uri: str) -> str | None:
    if uri.startswith(_WIKIDATA_ENTITY_PREFIX):
        tail = uri[len(_WIKIDATA_ENTITY_PREFIX) :]
        if tail.startswith("Q") and tail[1:].isdigit():
            return tail
    return None


def parse_sparql_statements(payload: dict[str, Any]) -> list[WikidataStatement]:
    """Adapt a ``application/sparql-results+json`` payload. Pure, for tests."""
    bindings = (payload.get("results") or {}).get("bindings") or []
    seen: set[str] = set()
    statements: list[WikidataStatement] = []
    for row in bindings:
        prop = row.get("prop") or {}
        prop_id = _qid_prop_id(prop.get("value", ""))
        if prop_id is None:
            continue
        value = row.get("value") or {}
        value_raw = value.get("value", "")
        value_qid = _qid_from_uri(value_raw) if value.get("type") == "uri" else None
        value_label = (row.get("valueLabel") or {}).get("value") or value_raw
        prop_label = (row.get("propLabel") or {}).get("value") or WIKIDATA_PROPERTY_LABELS.get(
            prop_id, prop_id
        )
        statement = WikidataStatement(
            property_id=prop_id,
            property_label=prop_label,
            value_label=value_label,
            value_qid=value_qid,
            value_url=(_WIKIDATA_ENTITY_PREFIX + value_qid) if value_qid else None,
        )
        if statement.statement_id not in seen:
            seen.add(statement.statement_id)
            statements.append(statement)
    return statements


def _qid_prop_id(uri: str) -> str | None:
    if uri.startswith(_WIKIDATA_ENTITY_PREFIX):
        tail = uri[len(_WIKIDATA_ENTITY_PREFIX) :]
        if tail.startswith("P") and tail[1:].isdigit():
            return tail
    return None


def parse_jsonld_statements(
    document: str | bytes | dict[str, Any], qid: str
) -> list[WikidataStatement]:
    """Adapt ``Special:EntityData/<QID>.jsonld`` via the vendored rdflib. Pure."""
    import json

    import rdflib

    safe_qid = _require_qid(qid)
    graph = rdflib.Graph()
    if isinstance(document, dict):
        document = json.dumps(document)
    graph.parse(data=document, format="json-ld")

    subject = rdflib.URIRef(_WIKIDATA_ENTITY_PREFIX + safe_qid)
    labels = _jsonld_labels(graph)
    seen: set[str] = set()
    statements: list[WikidataStatement] = []
    for predicate, obj in graph.predicate_objects(subject):
        pred_str = str(predicate)
        if not pred_str.startswith(_WIKIDATA_PROP_DIRECT):
            continue
        prop_id = pred_str[len(_WIKIDATA_PROP_DIRECT) :]
        value_qid = _qid_from_uri(str(obj)) if isinstance(obj, rdflib.URIRef) else None
        if value_qid is not None:
            value_label = labels.get(value_qid, value_qid)
        else:
            value_label = str(obj)
        statement = WikidataStatement(
            property_id=prop_id,
            property_label=WIKIDATA_PROPERTY_LABELS.get(prop_id, prop_id),
            value_label=value_label,
            value_qid=value_qid,
            value_url=(_WIKIDATA_ENTITY_PREFIX + value_qid) if value_qid else None,
        )
        if statement.statement_id not in seen:
            seen.add(statement.statement_id)
            statements.append(statement)
    statements.sort(key=lambda s: (s.property_label, s.value_label))
    return statements


def _jsonld_labels(graph: Any) -> dict[str, str]:
    import rdflib

    labels: dict[str, str] = {}
    rdfs_label = rdflib.RDFS.label
    for subject, obj in graph.subject_objects(rdfs_label):
        qid = _qid_from_uri(str(subject)) if isinstance(subject, rdflib.URIRef) else None
        if qid is None:
            continue
        lang = getattr(obj, "language", None)
        if qid not in labels or lang == "en":
            labels[qid] = str(obj)
    return labels


def statement_to_claim_text(subject_label: str, statement: WikidataStatement) -> str:
    """Human-readable claim text — the sentence the imported claim carries."""
    return f"{subject_label} — {statement.property_label}: {statement.value_label}"


async def fetch_statements_sparql(
    qid: str,
    endpoint: str = DEFAULT_WIKIDATA_SPARQL_ENDPOINT,
    *,
    lang: str = "en",
    client_factory: Callable[..., Any] | None = None,
) -> list[WikidataStatement]:
    """Run the statements SELECT against ``endpoint`` (bounded, opt-in caller).

    ``client_factory`` is injected in tests with a stub; production uses httpx.
    A failed fetch raises loudly — never a silent empty result or a fallback to
    a different endpoint. The caller (route) turns the raise into a clear error.
    """
    query = build_statements_query(qid, lang=lang)
    payload = await _sparql_json(endpoint, query, client_factory=client_factory)
    return parse_sparql_statements(payload)


async def _sparql_json(
    endpoint: str, query: str, *, client_factory: Callable[..., Any] | None = None
) -> dict[str, Any]:
    import httpx

    factory = client_factory or (lambda: httpx.AsyncClient(timeout=15.0))
    async with factory() as client:
        response = await client.get(
            endpoint,
            params={"query": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        return response.json()


async def fetch_statements_jsonld(
    qid: str, *, client_factory: Callable[..., Any] | None = None
) -> list[WikidataStatement]:
    """Fetch + parse ``Special:EntityData/<QID>.jsonld`` (endpoint-independent)."""
    import httpx

    safe_qid = _require_qid(qid)
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{safe_qid}.jsonld"
    factory = client_factory or (lambda: httpx.AsyncClient(timeout=15.0))
    async with factory() as client:
        response = await client.get(
            url, headers={"User-Agent": _USER_AGENT, "Accept": "application/ld+json"}
        )
        response.raise_for_status()
        text = response.text
    return parse_jsonld_statements(text, safe_qid)
