"""RDF triple substrate for the knowledge graph.

Phase A of the KG rollup (#899). Materializes KnowledgeEntity and
KnowledgeClaim rows as proper RDF triples so SPARQL queries become
available alongside the existing DuckDB joins. DuckDB stays the
canonical row store; rdflib is a queryable projection.

Ontology choices (standard W3C / schema.org vocabularies — interop
with any RDF tooling without translation):

- People → ``foaf:Person`` (FOAF is the lingua franca for personal
  identity in academic linked-data work).
- Places → ``schema:Place``.
- Organizations → ``schema:Organization``.
- Events → ``schema:Event``.
- Concepts → ``skos:Concept`` (SKOS is the standard for taxonomy /
  thesaurus vocabulary).
- Generic entity → ``schema:Thing`` fallback.

Claims become ``rdf:Statement`` reifications when they carry the
SVO triple in metadata — that's the cleanest way to attach
``epistemic_status`` / ``claim_type`` / ``source_excerpt`` to a
predicate edge without polluting the edge itself. For plain claims
without a structured predicate, we emit a single ``schema:about``
edge from the source document to the entity.

Storage: ``Graph()`` in-memory by default; ``persist(path)`` writes
N-Triples to disk. This is intentionally lightweight — no SQLite or
BerkeleyDB backend dependency. Engine code can rebuild the graph
from DuckDB any time, so the on-disk N-Triples file is a snapshot,
not a source of truth.

Future (#899 follow-ups):
- Phase D's splink linkage can read its candidate pairs out of
  SPARQL queries over this graph.
- Phase E's PyKEEN trains over the triples directly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import FOAF, RDF, RDFS, SKOS, XSD

from fichero_server.knowledge._common import enum_value, extract_svo, slug_verb

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

logger = logging.getLogger(__name__)


# Fichero's own namespace for IDs and predicates that don't have a
# standard schema.org / FOAF equivalent. Stable URI — don't rename
# after the first export ships, or external consumers' queries break.
FICHERO = Namespace("https://fichero.app/ns#")

# schema.org — vocab for events, places, organizations.
SCHEMA = Namespace("https://schema.org/")


def _entity_uri(entity_id: str) -> URIRef:
    """Stable URI for a KnowledgeEntity row."""
    return URIRef(f"https://fichero.app/entity/{quote(entity_id, safe='')}")


def _claim_uri(claim_id: str) -> URIRef:
    """Stable URI for a KnowledgeClaim row."""
    return URIRef(f"https://fichero.app/claim/{quote(claim_id, safe='')}")


def _doc_uri(document_id: str) -> URIRef:
    """Stable URI for a source Document row."""
    return URIRef(f"https://fichero.app/document/{quote(document_id, safe='')}")


def _entity_type_class(entity_type) -> URIRef:
    """Map ``EntityType`` enum to its preferred ontology class."""
    name = enum_value(entity_type)
    return {
        "person": FOAF.Person,
        "location": SCHEMA.Place,
        "organization": SCHEMA.Organization,
        "event": SCHEMA.Event,
        "concept": SKOS.Concept,
        "other": SCHEMA.Thing,
    }.get(name, SCHEMA.Thing)


def make_graph() -> Graph:
    """Create a fresh graph with our prefix bindings already set.

    The prefix bindings make N-Triples / Turtle output readable —
    consumers see ``foaf:Person`` rather than the full URI.
    """
    g = Graph()
    g.bind("fichero", FICHERO)
    g.bind("foaf", FOAF)
    g.bind("schema", SCHEMA)
    g.bind("skos", SKOS)
    g.bind("rdfs", RDFS)
    g.bind("rdf", RDF)
    return g


def entity_to_triples(graph: Graph, entity: "KnowledgeEntity") -> None:
    """Insert an entity's RDF triples into ``graph``.

    Triples emitted:
    - ``<entity> rdf:type <class>`` (one of FOAF.Person, schema:Place, etc.)
    - ``<entity> rdfs:label "canonical_name"@<lang?>``
    - ``<entity> skos:altLabel "alias"`` (one per alias)
    - ``<entity> rdfs:comment "description"`` (if present)
    - ``<entity> fichero:mergedInto <other>`` (when soft-deleted into another)
    """
    e_uri = _entity_uri(entity.id)
    graph.add((e_uri, RDF.type, _entity_type_class(entity.entity_type)))

    label = Literal(entity.canonical_name, lang=entity.language) if entity.language else Literal(entity.canonical_name)
    graph.add((e_uri, RDFS.label, label))

    for alias in (entity.aliases or []):
        graph.add((e_uri, SKOS.altLabel, Literal(alias)))

    if entity.description:
        graph.add((e_uri, RDFS.comment, Literal(entity.description)))

    if entity.merged_into_id:
        graph.add((e_uri, FICHERO.mergedInto, _entity_uri(entity.merged_into_id)))


def _predicate_uri(verb: str) -> URIRef:
    """Mint a stable predicate URI from an SVO verb.

    The verb gets slugified into the ``fichero:`` namespace. Two claims
    that share the same verb share the same predicate URI, which is
    the property RDF reasoners exploit — once you've asserted
    ``Pérez fichero:signedDeed Deed``, SPARQL can find every other
    signing event without rescanning the claim text.

    Slug rules: lowercase, alphanumerics + dashes, no leading digits.
    Empty verbs map to a generic ``fichero:assertedAbout`` so we never
    drop a claim from the graph. Slug rules live in
    ``fichero_server.knowledge._common.slug_verb`` so SPARQL queries over this graph
    agree with the in-Python aggregation in ``triangulation``.
    """
    return URIRef(str(FICHERO) + slug_verb(verb))


def claim_to_triples(
    graph: Graph,
    claim: "KnowledgeClaim",
    entities: Optional[dict[str, "KnowledgeEntity"]] = None,
) -> None:
    """Insert a claim's RDF triples into ``graph``.

    Two patterns depending on whether the claim has a structured SVO:

    **Structured SVO** (verb + object in ``metadata`` from #892):
    - For each ``entity_id``, emit ``<entity> <predicate> <object>``
      where predicate is the slugified verb and object is the literal
      string from ``metadata['object']``.
    - Additionally emit a reified ``rdf:Statement`` carrying the
      epistemic_status, claim_type, source_document_id, page_label,
      and source_excerpt — these are claim-level properties that
      don't fit on an edge.

    **Unstructured** (legacy ``context`` shape):
    - Emit ``<doc> schema:about <entity>`` per entity, plus the same
      reified statement for the claim-level metadata.

    Pass ``entities`` to enrich object literals with entity labels when
    the object phrase happens to match a known entity's canonical name
    — this is the seed of the cross-entity link prediction PyKEEN will
    train on at Phase E.
    """
    c_uri = _claim_uri(claim.id)
    doc_uri = _doc_uri(claim.source_document_id)
    verb, obj_text = extract_svo(claim)
    predicate = _predicate_uri(verb)

    # Reified statement: carries claim-level metadata that doesn't fit
    # on an edge. Standard RDF pattern, queryable in SPARQL.
    graph.add((c_uri, RDF.type, RDF.Statement))
    graph.add((c_uri, FICHERO.sourceDocument, doc_uri))
    if claim.source_page_label:
        graph.add((c_uri, FICHERO.sourcePageLabel, Literal(claim.source_page_label)))
    if claim.source_excerpt:
        graph.add((c_uri, FICHERO.sourceExcerpt, Literal(claim.source_excerpt)))
    if claim.epistemic_status:
        graph.add((c_uri, FICHERO.epistemicStatus, Literal(enum_value(claim.epistemic_status))))
    if claim.claim_type:
        graph.add((c_uri, FICHERO.claimType, Literal(enum_value(claim.claim_type))))
    if claim.confidence is not None:
        graph.add((c_uri, FICHERO.confidence, Literal(float(claim.confidence), datatype=XSD.float)))

    # The actual subject-predicate-object edges.
    for entity_id in (claim.entity_ids or []):
        subj_uri = _entity_uri(entity_id)
        if verb and obj_text:
            # Try to resolve the object against known entities for a
            # proper resource-to-resource edge; fall back to literal.
            obj_node: URIRef | Literal = Literal(obj_text)
            if entities:
                for ent in entities.values():
                    if ent.canonical_name == obj_text or obj_text in (ent.aliases or []):
                        obj_node = _entity_uri(ent.id)
                        break
            graph.add((subj_uri, predicate, obj_node))
        else:
            # No structured predicate — emit the document mention edge.
            graph.add((doc_uri, SCHEMA.about, subj_uri))

        # Always link the claim back to each subject for reification.
        graph.add((c_uri, RDF.subject, subj_uri))
        graph.add((c_uri, RDF.predicate, predicate))
        if obj_text:
            graph.add((c_uri, RDF.object, Literal(obj_text)))


def build_graph(
    entities: Iterable["KnowledgeEntity"],
    claims: Iterable["KnowledgeClaim"],
) -> Graph:
    """Build a full graph from iterables of entities + claims.

    O(N) over the entity + claim count. For typical Fichero libraries
    (a few thousand entities, low-five-digit claims) this runs in
    well under a second and produces a graph small enough to keep
    in memory.
    """
    g = make_graph()
    entity_index: dict[str, "KnowledgeEntity"] = {}
    for ent in entities:
        entity_to_triples(g, ent)
        entity_index[ent.id] = ent
    for claim in claims:
        claim_to_triples(g, claim, entity_index)
    return g


def persist(graph: Graph, path: Path | str, format: str = "nt") -> None:
    """Serialize the graph to disk.

    Default is N-Triples (one statement per line, line-grep friendly,
    streamable). Pass ``format='turtle'`` or ``format='json-ld'`` for
    other shapes. Path is created if missing.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Pass encoding explicitly: rdflib's NTSerializer warns when encoding
    # is None (it always uses UTF-8 anyway), and UTF-8 is the right
    # choice for turtle / json-ld too. (#1026)
    graph.serialize(destination=str(p), format=format, encoding="utf-8")


def sparql(graph: Graph, query: str):
    """Run a SPARQL query against ``graph`` and return result rows.

    Convenience wrapper so callers don't need to import rdflib
    directly. Examples:

        rows = sparql(graph,
            "SELECT ?p WHERE { ?p a foaf:Person ; rdfs:label ?n . "
            "FILTER(CONTAINS(LCASE(STR(?n)), 'davidson')) }"
        )
    """
    return list(graph.query(query))


__all__ = [name for name in globals() if not name.startswith("__")]
