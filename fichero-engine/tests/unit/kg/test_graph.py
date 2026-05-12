"""Tests for the NetworkX-backed KG analytics module (#376)."""

from __future__ import annotations

import networkx as nx

from fichero.kg import graph
from fichero.knowledge_models import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _ent(id_: str, name: str, etype=EntityType.person) -> KnowledgeEntity:
    return KnowledgeEntity(id=id_, canonical_name=name, entity_type=etype)


def _claim(
    *, claim_id: str, doc: str, subject_id: str,
    verb: str = "mentions", obj: str = "something",
) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id,
        text=f"{subject_id} {verb} {obj}",
        source_document_id=doc,
        entity_ids=[subject_id],
        metadata={"verb": verb, "object": obj},
    )


class TestBuildGraph:
    def test_creates_one_node_per_entity(self):
        ents = [_ent("e-1", "Davidson"), _ent("e-2", "Eugenio")]
        g = graph.build_graph(ents, claims=[])
        assert "e-1" in g.nodes
        assert "e-2" in g.nodes
        assert g.nodes["e-1"][graph.NODE_NAME] == "Davidson"

    def test_svo_claim_creates_directed_edge(self):
        ents = [_ent("e-1", "Juan")]
        cl = _claim(
            claim_id="c-1", doc="doc-1", subject_id="e-1",
            verb="signed", obj="the deed",
        )
        g = graph.build_graph(ents, [cl])
        # Object resolves to a literal node since no matching entity
        # named "the deed" exists; edge from Juan → literal.
        out_edges = list(g.out_edges("e-1", data=True))
        assert len(out_edges) == 1
        _src, _tgt, data = out_edges[0]
        assert data[graph.EDGE_PREDICATE] == "signed"
        assert data[graph.EDGE_CLAIM_ID] == "c-1"

    def test_object_resolves_to_entity_when_canonical_match(self):
        subj = _ent("e-1", "Juan")
        target = _ent("e-2", "The Deed", etype=EntityType.other)
        cl = _claim(
            claim_id="c-1", doc="doc-1", subject_id="e-1",
            verb="signed", obj="The Deed",
        )
        g = graph.build_graph([subj, target], [cl])
        # Direct entity-to-entity edge.
        assert g.has_edge("e-1", "e-2")

    def test_object_resolves_via_alias(self):
        subj = _ent("e-1", "Davidson")
        target = KnowledgeEntity(
            id="e-2", canonical_name="The Letter",
            entity_type=EntityType.other,
            aliases=["the missive"],
        )
        cl = _claim(
            claim_id="c-1", doc="doc-1", subject_id="e-1",
            verb="signed", obj="the missive",
        )
        g = graph.build_graph([subj, target], [cl])
        assert g.has_edge("e-1", "e-2")


class TestCooccurrence:
    def test_two_entities_in_same_doc_have_edge(self):
        ents = [_ent("e-1", "Juan"), _ent("e-2", "Eugenio")]
        claims = [
            _claim(claim_id="c-1", doc="doc-A", subject_id="e-1"),
            _claim(claim_id="c-2", doc="doc-A", subject_id="e-2"),
        ]
        g = graph.cooccurrence_graph(ents, claims)
        assert g.has_edge("e-1", "e-2")
        assert g["e-1"]["e-2"]["weight"] == 1

    def test_repeated_co_occurrence_accumulates_weight(self):
        ents = [_ent("e-1", "Juan"), _ent("e-2", "Eugenio")]
        claims = [
            _claim(claim_id="c-1", doc="doc-A", subject_id="e-1"),
            _claim(claim_id="c-2", doc="doc-A", subject_id="e-2"),
            _claim(claim_id="c-3", doc="doc-B", subject_id="e-1"),
            _claim(claim_id="c-4", doc="doc-B", subject_id="e-2"),
        ]
        g = graph.cooccurrence_graph(ents, claims)
        assert g["e-1"]["e-2"]["weight"] == 2

    def test_no_co_occurrence_no_edge(self):
        ents = [_ent("e-1", "Juan"), _ent("e-2", "Eugenio")]
        claims = [
            _claim(claim_id="c-1", doc="doc-A", subject_id="e-1"),
            _claim(claim_id="c-2", doc="doc-B", subject_id="e-2"),
        ]
        g = graph.cooccurrence_graph(ents, claims)
        assert not g.has_edge("e-1", "e-2")


class TestCentrality:
    def test_empty_graph_returns_empty_list(self):
        scores = graph.centrality(nx.Graph(), top_k=10)
        assert scores == []

    def test_hub_node_ranks_highest(self):
        """A star graph where one node connects to all others should
        have the hub at the top of the centrality ranking."""
        g = nx.Graph()
        g.add_node("hub", canonical_name="Hub", entity_type="person")
        for i in range(5):
            g.add_node(f"leaf-{i}", canonical_name=f"Leaf {i}", entity_type="person")
            g.add_edge("hub", f"leaf-{i}", weight=1)
        scores = graph.centrality(g, top_k=3)
        assert scores[0].entity_id == "hub"
        assert scores[0].degree == 5

    def test_only_type_filters_subgraph(self):
        g = nx.Graph()
        g.add_node("p-1", canonical_name="P1", entity_type="person")
        g.add_node("p-2", canonical_name="P2", entity_type="person")
        g.add_node("l-1", canonical_name="L1", entity_type="location")
        g.add_edge("p-1", "p-2")
        g.add_edge("p-1", "l-1")
        scores = graph.centrality(g, top_k=10, only_type="person")
        ids = {s.entity_id for s in scores}
        assert "l-1" not in ids
        assert "p-1" in ids and "p-2" in ids


class TestShortestPath:
    def test_finds_path_through_intermediate(self):
        g = nx.MultiDiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        path = graph.shortest_path_entities(g, "a", "c")
        assert path == ["a", "b", "c"]

    def test_no_path_returns_empty(self):
        g = nx.MultiDiGraph()
        g.add_node("a")
        g.add_node("b")
        assert graph.shortest_path_entities(g, "a", "b") == []

    def test_missing_node_returns_empty(self):
        g = nx.MultiDiGraph()
        g.add_node("a")
        assert graph.shortest_path_entities(g, "a", "z") == []
