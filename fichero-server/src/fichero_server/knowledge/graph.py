"""NetworkX-backed graph analytics over the KG (#376, #899 follow-on).

Builds a ``networkx.MultiDiGraph`` from the canonical
KnowledgeEntity + KnowledgeClaim tables and exposes traversal +
centrality queries that the DuckDB SQL store can't answer
ergonomically:

- **Co-occurrence**: which entities appear in the same source
  documents → adjacency for the "people who were there together"
  query.
- **Centrality**: degree / betweenness / eigenvector centrality
  surfaces which entities are connector hubs vs. peripheral
  mentions.
- **Path-finding**: shortest path between two entities through the
  claim graph. Drives the hermeneutics "show me how A connects to
  B" view.
- **Contradiction networks**: subgraphs of claims linked by
  ``contradicts`` claim links (KnowledgeClaimLink), surfacing the
  controversy zones the historiography UI needs.

DuckDB stays canonical; the NetworkX graph is a derived view rebuilt
on demand or on a refresh schedule.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Optional

import networkx as nx

from fichero_server.kg._common import enum_value, extract_svo

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.db import Database
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

logger = logging.getLogger(__name__)


# Node attribute keys — kept as constants so consumers don't have
# to remember the magic strings.
NODE_NAME = "canonical_name"
NODE_TYPE = "entity_type"
NODE_ALIASES = "aliases"

# Edge attribute keys.
EDGE_CLAIM_ID = "claim_id"
EDGE_PREDICATE = "predicate"
EDGE_SOURCE_DOC = "source_document_id"
EDGE_PAGE_LABEL = "source_page_label"
EDGE_EPISTEMIC = "epistemic_status"


@dataclass(frozen=True)
class CentralityScore:
    """One entity's centrality reading across the standard metrics."""
    entity_id: str
    canonical_name: str
    degree: int
    betweenness: float
    eigenvector: float


def build_graph(
    entities: Iterable["KnowledgeEntity"],
    claims: Iterable["KnowledgeClaim"],
) -> nx.MultiDiGraph:
    """Build a NetworkX directed multi-graph from KG rows.

    Nodes: KnowledgeEntity (keyed by entity.id). Attributes carry
    canonical_name + entity_type + aliases for downstream queries.

    Edges: KnowledgeClaim — each claim with an SVO predicate becomes
    one directed edge per linked entity (subject → object-as-entity
    when the object resolves to a known canonical_name; otherwise
    just an outgoing edge with the object as edge text). MultiDiGraph
    so multiple claims about the same pair don't collide.

    Claims without verb/object (legacy ``context``-only shape) still
    produce edges from the source document to each entity via a
    ``mentions`` predicate so traversal works on legacy data too.
    """
    g = nx.MultiDiGraph()

    # Index entities by canonical name + lowered name + alias for
    # later object-text → entity resolution.
    name_to_id: dict[str, str] = {}
    for ent in entities:
        g.add_node(
            ent.id,
            **{
                NODE_NAME: ent.canonical_name,
                NODE_TYPE: enum_value(ent.entity_type),
                NODE_ALIASES: list(ent.aliases or []),
            },
        )
        name_to_id[ent.canonical_name.lower()] = ent.id
        for alias in (ent.aliases or []):
            name_to_id.setdefault(alias.lower(), ent.id)

    for claim in claims:
        verb, obj_text = extract_svo(claim)
        predicate = verb or "mentions"

        for subject_id in (claim.entity_ids or []):
            if subject_id not in g:
                # Skip orphaned entity reference — claim says e-1 but
                # we don't have e-1 in the entities iterable.
                continue
            # Try to resolve object to a known entity.
            object_id = name_to_id.get(obj_text.lower()) if obj_text else None
            target = object_id or f"object:{obj_text}" if obj_text else None
            if target and target not in g:
                # Object is a literal string, not an entity — add a
                # lightweight literal node so the edge has somewhere
                # to land.
                g.add_node(target, **{NODE_NAME: obj_text, NODE_TYPE: "literal"})
            if target:
                g.add_edge(
                    subject_id,
                    target,
                    **{
                        EDGE_CLAIM_ID: claim.id,
                        EDGE_PREDICATE: predicate,
                        EDGE_SOURCE_DOC: claim.source_document_id,
                        EDGE_PAGE_LABEL: claim.source_page_label or "",
                        EDGE_EPISTEMIC: enum_value(claim.epistemic_status) if claim.epistemic_status else "",
                    },
                )

    return g


def cooccurrence_graph(
    entities: Iterable["KnowledgeEntity"],
    claims: Iterable["KnowledgeClaim"],
) -> nx.Graph:
    """Undirected co-occurrence: entities sharing a source document.

    Edge weight = number of distinct source documents in which both
    endpoints appear. Use case: "show me people who were in the
    same archive folder" — the surface that maps to an
    archival research workflow.
    """
    g = nx.Graph()
    for ent in entities:
        g.add_node(
            ent.id,
            **{
                NODE_NAME: ent.canonical_name,
                NODE_TYPE: enum_value(ent.entity_type),
            },
        )

    # docs[doc_id] = set of entity_ids mentioned in that document.
    docs: dict[str, set[str]] = defaultdict(set)
    for claim in claims:
        for entity_id in (claim.entity_ids or []):
            docs[claim.source_document_id].add(entity_id)

    # For each document, every pair of co-mentioned entities gets +1.
    for entity_set in docs.values():
        ents = list(entity_set)
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                a, b = ents[i], ents[j]
                if g.has_edge(a, b):
                    g[a][b]["weight"] += 1
                else:
                    g.add_edge(a, b, weight=1)

    return g


@dataclass(frozen=True)
class MergeCandidate:
    """A pair of entities a graph-context heuristic thinks are the same.

    Surfaced into the review queue (#988) so a human accepts/rejects —
    never auto-merged. ``jaccard`` is the neighbour-set Jaccard index;
    ``shared_neighbours`` is the raw overlap count so the reviewer can
    distinguish "2 of 3 neighbours shared" from "20 of 40 shared".
    """
    entity_a_id: str
    entity_b_id: str
    name_a: str
    name_b: str
    shared_neighbours: int
    jaccard: float


def graph_context_merge_candidates(
    g: nx.Graph,
    *,
    threshold: float = 0.5,
    min_shared: int = 2,
    same_type_only: bool = True,
    top_k: Optional[int] = None,
) -> list[MergeCandidate]:
    """Propose entity-merge candidates from co-occurrence neighbourhood overlap.

    The entity-resolution gap (#988): name/alias matching misses
    duplicates that never share a surface form — "Andrés" and "Andrés
    Restrepo" extracted as two entities. But if they're the same
    person, they tend to be co-mentioned with the *same other people*.
    High Jaccard overlap of their co-occurrence neighbourhoods is that
    signal.

    Built on ``nx.jaccard_coefficient``, which by design scores only
    *non-adjacent* pairs — two entities co-mentioned in the same doc
    already have an edge and aren't candidates here; we want the pair
    that shares a neighbourhood but was never co-mentioned directly.

    Args:
        g: an undirected co-occurrence graph from ``cooccurrence_graph``.
        threshold: minimum Jaccard index to propose a merge.
        min_shared: minimum raw count of shared neighbours — guards
            against a 1.0 Jaccard from two entities that each have a
            single, shared neighbour (degenerate, not evidence).
        same_type_only: when True, only pair entities of the same
            ``entity_type`` — a person and a place sharing neighbours
            is graph noise, not a duplicate.
        top_k: cap the result; None returns every candidate over
            threshold. Results are always sorted strongest-first.

    Returns:
        ``MergeCandidate`` rows sorted by descending Jaccard, then by
        descending shared-neighbour count.
    """
    if g.number_of_nodes() < 2:
        return []

    candidates: list[MergeCandidate] = []
    for a, b, score in nx.jaccard_coefficient(g):
        if score < threshold:
            continue
        if same_type_only and (
            g.nodes[a].get(NODE_TYPE) != g.nodes[b].get(NODE_TYPE)
        ):
            continue
        shared = len(set(g.neighbors(a)) & set(g.neighbors(b)))
        if shared < min_shared:
            continue
        candidates.append(MergeCandidate(
            entity_a_id=a,
            entity_b_id=b,
            name_a=g.nodes[a].get(NODE_NAME, ""),
            name_b=g.nodes[b].get(NODE_NAME, ""),
            shared_neighbours=shared,
            jaccard=score,
        ))

    candidates.sort(key=lambda c: (-c.jaccard, -c.shared_neighbours))
    return candidates[:top_k] if top_k is not None else candidates


def centrality(
    g: nx.Graph,
    top_k: int = 20,
    only_type: Optional[str] = None,
) -> list[CentralityScore]:
    """Compute degree / betweenness / eigenvector centrality and
    return the top-k entities ranked by composite score.

    ``only_type`` filters to one EntityType (e.g. "person") before
    ranking. Useful for "who are the most central people in this
    library" vs "what locations connect the most claims."

    Composite score = degree (z-score) + betweenness (z-score) +
    eigenvector (z-score). Equal weighting — Phase D's splink work
    could later learn the weights from labelled importance pairs.
    """
    if not g.nodes:
        return []

    # Filter nodes by type if requested. The subgraph keeps edges
    # only between same-type pairs — that's the right semantic for
    # "who's central in the people network."
    if only_type:
        keep = [n for n, attrs in g.nodes(data=True) if attrs.get(NODE_TYPE) == only_type]
        h = g.subgraph(keep).copy()
    else:
        h = g

    if not h.nodes:
        return []

    deg = dict(h.degree())
    # Betweenness is O(N^3) — fine for typical libraries (~1000s of
    # entities) but cap node count for safety on huge corpora.
    if len(h) <= 5000:
        between = nx.betweenness_centrality(h)
    else:
        between = {n: 0.0 for n in h.nodes}
    try:
        eig = nx.eigenvector_centrality(h, max_iter=200)
    except (nx.PowerIterationFailedConvergence, nx.NetworkXException):
        # Eigenvector centrality can fail on disconnected components.
        # Fall back to zeroes — degree + betweenness still drive the
        # ranking.
        eig = {n: 0.0 for n in h.nodes}

    # Z-scores for composite ranking.
    def _zscores(values: dict[str, float]) -> dict[str, float]:
        if not values:
            return {}
        xs = list(values.values())
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / len(xs)
        std = var ** 0.5 or 1.0
        return {k: (v - mean) / std for k, v in values.items()}

    z_deg = _zscores({n: float(d) for n, d in deg.items()})
    z_bet = _zscores(between)
    z_eig = _zscores(eig)

    rows: list[CentralityScore] = []
    for node in h.nodes:
        composite = z_deg.get(node, 0) + z_bet.get(node, 0) + z_eig.get(node, 0)
        rows.append((composite, CentralityScore(
            entity_id=node,
            canonical_name=h.nodes[node].get(NODE_NAME, ""),
            degree=deg.get(node, 0),
            betweenness=between.get(node, 0.0),
            eigenvector=eig.get(node, 0.0),
        )))
    rows.sort(key=lambda pair: -pair[0])
    return [score for _, score in rows[:top_k]]


def shortest_path_entities(
    g: nx.MultiDiGraph,
    source_id: str,
    target_id: str,
) -> list[str]:
    """Shortest path between two entity nodes as a list of entity ids.

    Returns ``[]`` when no path exists. The path is along directed
    SVO claim edges, so a result like ``[A, B, C]`` reads as "A
    asserts something about B, and B asserts something about C."

    For an undirected "how are they connected" view, run this
    against the cooccurrence_graph instead.
    """
    try:
        if isinstance(g, nx.DiGraph):
            return nx.shortest_path(g, source=source_id, target=target_id)
        return nx.shortest_path(g, source=source_id, target=target_id)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def contradiction_subgraph(
    db: "Database",
) -> nx.Graph:
    """Build the contradiction sub-network from KnowledgeClaimLink rows.

    Two claims connected by a ``contradicts`` link become an edge.
    Claims connected by ``supports`` are NOT edges here — supports
    reinforces a single thread, contradicts marks the controversy.

    Use case: the "controversy zones" view from #376's acceptance
    criteria. Communities in this graph are clusters of claims that
    disagree with each other — primary candidates for hermeneutic
    interpretation.
    """
    from fichero_server.models.knowledge import (
        ClaimRelationType,
        KnowledgeClaim,
        KnowledgeClaimLink,
    )

    g = nx.Graph()
    # Nodes: every claim referenced by any link.
    relevant_links = [
        link for link in db.query(KnowledgeClaimLink)
        if link.relation == ClaimRelationType.contradicts
    ]
    if not relevant_links:
        return g

    claim_ids = set()
    for link in relevant_links:
        claim_ids.add(link.source_claim_id)
        claim_ids.add(link.target_claim_id)
    for claim_id in claim_ids:
        claim = db.get(KnowledgeClaim, claim_id)
        if claim is None:
            continue
        g.add_node(claim_id, text=claim.text[:160])

    for link in relevant_links:
        g.add_edge(link.source_claim_id, link.target_claim_id, weight=1)

    return g


# Library-scoped graph cache keyed by (db_path, latest_claim_signature).
# Invalidated when any claim or entity is written — we recompute the
# signature on every call and rebuild when it changes. Memory cost is
# bounded by the number of libraries the process touches; ~10 MB per
# cached graph at 50K claims. Without this cache every API call that
# touches build_full_graph (18 endpoints in kg_graph.py) does a full
# DuckDB scan + rebuild — 3-5s at 50K claims, freezes the UI.
# (#990 — scaling-review bottleneck 1)
_DIRECTED_CACHE: dict[str, tuple[tuple, nx.MultiDiGraph]] = {}
_COOC_CACHE: dict[str, tuple[tuple, nx.Graph]] = {}


def _cache_signature(db: "Database") -> tuple:
    """Build the cache invalidation key.

    Cheap aggregate query (~1ms even on 1M rows): count + max(updated_at)
    on both tables. Captures inserts, deletes, AND mutations to existing
    rows. Returns a hashable tuple suitable as the dict-cache value.
    """
    try:
        claims = db.knowledge_table_signature("knowledgeclaims")
    except Exception:
        claims = (0, None)
    try:
        entities = db.knowledge_table_signature("knowledgeentitys")
    except Exception:
        entities = (0, None)
    # Stringify timestamps so the tuple is hashable / comparable
    # consistently across DuckDB result types.
    return (
        int(claims[0] or 0),
        str(claims[1]) if claims[1] is not None else "",
        int(entities[0] or 0),
        str(entities[1]) if entities[1] is not None else "",
    )


def _build_cached(db: "Database", builder, cache: dict):
    """Shared cache lookup + build path for the full-library graphs.

    Both ``build_full_graph`` and ``build_full_cooccurrence`` follow
    the exact same lookup / rebuild / store sequence — only the
    builder function and which cache dict they write to differs.
    """
    from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

    key = str(db.path)
    signature = _cache_signature(db)
    cached = cache.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]
    graph = builder(
        entities=db.query(KnowledgeEntity),
        claims=db.query(KnowledgeClaim),
    )
    cache[key] = (signature, graph)
    return graph


def build_full_graph(db: "Database") -> nx.MultiDiGraph:
    """Convenience: build the directed claim graph from the whole library.

    Library-scoped LRU cache (#990) — re-uses the cached graph when the
    knowledgeclaims + knowledgeentitys tables haven't changed since the
    last call. Cuts hot-path latency from 3-5s to ~1ms (signature query)
    on warm cache at 50K claims.
    """
    return _build_cached(db, build_graph, _DIRECTED_CACHE)


def build_full_cooccurrence(db: "Database") -> nx.Graph:
    """Convenience: build the undirected co-occurrence graph from the whole library.

    Library-scoped LRU cache (#990) — see ``build_full_graph``.
    """
    return _build_cached(db, cooccurrence_graph, _COOC_CACHE)


def invalidate_graph_cache(db: "Database" | None = None) -> None:
    """Drop cached graphs for one library (or all).

    Callers don't usually need this — the signature check picks up
    changes automatically. Exposed for tests + the rebuild_kg pipeline
    which wants to force a re-derive after a known-write.
    """
    if db is None:
        _DIRECTED_CACHE.clear()
        _COOC_CACHE.clear()
        return
    key = str(db.path)
    _DIRECTED_CACHE.pop(key, None)
    _COOC_CACHE.pop(key, None)


__all__ = [name for name in globals() if not name.startswith("__")]
