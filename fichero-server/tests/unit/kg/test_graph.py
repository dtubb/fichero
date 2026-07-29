"""Tests for the NetworkX-backed KG analytics module (#376)."""

from __future__ import annotations

import networkx as nx

from fichero_server.kg import graph
from fichero_server.models.knowledge import (
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


class TestGraphContextMergeCandidates:
    """#988 — graph-context similarity candidate generator.

    Two entities that share many co-occurrence neighbours but were
    never co-mentioned directly are likely the same entity seen under
    two surface forms. These tests lock the Jaccard-over-neighbourhood
    contract: threshold, min-shared guard, same-type filter, ordering.
    """

    @staticmethod
    def _typed_graph() -> nx.Graph:
        """a and b each connect to the same 3 hubs, never to each other.

        Jaccard(a, b) over neighbour sets = 3/3 = 1.0, shared = 3.
        """
        g = nx.Graph()
        for nid, name, etype in [
            ("a", "Andrés", "person"),
            ("b", "Andrés Restrepo", "person"),
            ("h1", "Cheryl", "person"),
            ("h2", "Popayán", "place"),
            ("h3", "1933 Petition", "event"),
        ]:
            g.add_node(nid, **{graph.NODE_NAME: name, graph.NODE_TYPE: etype})
        for hub in ("h1", "h2", "h3"):
            g.add_edge("a", hub, weight=1)
            g.add_edge("b", hub, weight=1)
        return g

    def test_high_overlap_pair_is_proposed(self):
        g = self._typed_graph()
        candidates = graph.graph_context_merge_candidates(g, threshold=0.5)
        pair = {(c.entity_a_id, c.entity_b_id) for c in candidates}
        assert ("a", "b") in pair or ("b", "a") in pair
        cand = next(c for c in candidates if {c.entity_a_id, c.entity_b_id} == {"a", "b"})
        assert cand.jaccard == 1.0
        assert cand.shared_neighbours == 3
        assert {cand.name_a, cand.name_b} == {"Andrés", "Andrés Restrepo"}

    def test_directly_connected_pair_is_not_a_candidate(self):
        """nx.jaccard_coefficient scores only non-adjacent pairs — a pair
        already co-mentioned in a doc has an edge and is excluded."""
        g = self._typed_graph()
        g.add_edge("a", "b", weight=1)
        candidates = graph.graph_context_merge_candidates(g, threshold=0.5)
        assert not any(
            {c.entity_a_id, c.entity_b_id} == {"a", "b"} for c in candidates
        )

    def test_threshold_filters_low_overlap(self):
        g = self._typed_graph()
        # Give a and b one private neighbour each → Jaccard drops to 3/5.
        g.add_node("xa", **{graph.NODE_NAME: "xa", graph.NODE_TYPE: "person"})
        g.add_node("xb", **{graph.NODE_NAME: "xb", graph.NODE_TYPE: "person"})
        g.add_edge("a", "xa")
        g.add_edge("b", "xb")
        assert graph.graph_context_merge_candidates(g, threshold=0.7) == []
        assert graph.graph_context_merge_candidates(g, threshold=0.6) != []

    def test_min_shared_guards_against_single_shared_neighbour(self):
        """Two entities each with one neighbour, the same one → Jaccard
        1.0 but only 1 shared neighbour: not evidence, must be dropped."""
        g = nx.Graph()
        for nid in ("a", "b", "h1"):
            g.add_node(nid, **{graph.NODE_NAME: nid, graph.NODE_TYPE: "person"})
        g.add_edge("a", "h1")
        g.add_edge("b", "h1")
        assert graph.graph_context_merge_candidates(g, min_shared=2) == []
        assert graph.graph_context_merge_candidates(g, min_shared=1) != []

    def test_same_type_only_filters_cross_type_pairs(self):
        g = self._typed_graph()
        # Flip b to a place — a person and a place sharing neighbours is
        # graph noise, not a duplicate.
        g.nodes["b"][graph.NODE_TYPE] = "place"
        assert graph.graph_context_merge_candidates(g, same_type_only=True) == []
        assert graph.graph_context_merge_candidates(g, same_type_only=False) != []

    def test_results_sorted_strongest_first(self):
        g = self._typed_graph()
        # Add a second weaker pair c/d sharing 2 of 3 hubs.
        for nid in ("c", "d"):
            g.add_node(nid, **{graph.NODE_NAME: nid, graph.NODE_TYPE: "person"})
        g.add_edge("c", "h1")
        g.add_edge("c", "h2")
        g.add_edge("d", "h1")
        g.add_edge("d", "h2")
        g.add_node("h4", **{graph.NODE_NAME: "h4", graph.NODE_TYPE: "person"})
        g.add_edge("c", "h4")  # c has a private neighbour → lower Jaccard
        candidates = graph.graph_context_merge_candidates(g, threshold=0.4)
        jaccards = [c.jaccard for c in candidates]
        assert jaccards == sorted(jaccards, reverse=True)

    def test_top_k_caps_results(self):
        g = self._typed_graph()
        for nid in ("c", "d"):
            g.add_node(nid, **{graph.NODE_NAME: nid, graph.NODE_TYPE: "person"})
        for hub in ("h1", "h2", "h3"):
            g.add_edge("c", hub)
            g.add_edge("d", hub)
        all_candidates = graph.graph_context_merge_candidates(g, threshold=0.5)
        assert len(all_candidates) > 1
        assert len(graph.graph_context_merge_candidates(g, threshold=0.5, top_k=1)) == 1

    def test_empty_graph_returns_empty(self):
        assert graph.graph_context_merge_candidates(nx.Graph()) == []

    def test_integrates_with_cooccurrence_graph(self):
        """End-to-end: build a co-occurrence graph from claims where a
        hidden duplicate shares a neighbourhood, and confirm the
        candidate surfaces."""
        ents = [
            _ent("andres", "Andrés"),
            _ent("andres-r", "Andrés Restrepo"),
            _ent("cheryl", "Cheryl"),
            _ent("matthew", "Matthew"),
        ]
        # doc-1: Andrés co-mentioned with Cheryl + Matthew.
        # doc-2: Andrés Restrepo co-mentioned with Cheryl + Matthew.
        # Andrés and Andrés Restrepo never share a doc → non-adjacent,
        # but identical neighbourhoods.
        claims = [
            KnowledgeClaim(
                id="c1", text="x", source_document_id="doc-1",
                entity_ids=["andres", "cheryl", "matthew"],
            ),
            KnowledgeClaim(
                id="c2", text="y", source_document_id="doc-2",
                entity_ids=["andres-r", "cheryl", "matthew"],
            ),
        ]
        g = graph.cooccurrence_graph(ents, claims)
        candidates = graph.graph_context_merge_candidates(g, threshold=0.5)
        assert any(
            {c.entity_a_id, c.entity_b_id} == {"andres", "andres-r"}
            for c in candidates
        )
