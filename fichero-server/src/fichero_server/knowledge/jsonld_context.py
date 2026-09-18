"""Named JSON-LD ``@context`` profiles for KG RDF export (#4753).

The export's ``@context`` is selectable by design (kg-enrichment spec).
Only ``schema-org`` ships today -- it is a real, static
JSON-LD context that documents the vocabulary ``knowledge.triples`` already
emits (``foaf:Person``, ``schema:Place``/``Organization``/``Event``,
``skos:Concept``, ``rdfs:label``/``comment``, and Fichero's own
``fichero:`` predicates). rdflib's default JSON-LD serializer would
otherwise auto-generate an equivalent context from the graph's bound
prefixes at export time; this module makes that context an explicit,
reviewable artifact instead of an implicit side effect, and shapes the
registry so a second profile is exactly one more dict.

Linked Art / CIDOC-CRM (the other two profiles the kg-enrichment spec
names as selectable) are real museum/archival ontologies -- ``E21_Person``,
``E53_Place`` and friends carry curatorial meaning. Mapping Fichero's
model onto them is a domain decision that needs the maintainer's review,
not an engine-side guess, so they are deliberately NOT stubbed
here (an option that would raise if picked is a needless toggle) --
tracked as a follow-up issue on the kg-enrichment milestone instead.
"""

from __future__ import annotations

from fichero_server.knowledge.triples import FICHERO, SCHEMA

#: The context `knowledge.triples.make_graph()` already binds, made
#: explicit. Order matches `make_graph()`'s bind() calls for easy diffing.
SCHEMA_ORG_CONTEXT: dict[str, str] = {
    "fichero": str(FICHERO),
    "foaf": "http://xmlns.com/foaf/0.1/",
    "schema": str(SCHEMA),
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}

#: profile name -> @context dict. The KG export route's `context` query
#: param is typed against this registry's keys (see `api/routes/kg/sparql.py`).
JSONLD_CONTEXTS: dict[str, dict[str, str]] = {
    "schema-org": SCHEMA_ORG_CONTEXT,
}

__all__ = ["SCHEMA_ORG_CONTEXT", "JSONLD_CONTEXTS"]
