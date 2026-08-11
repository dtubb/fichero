"""Backend coverage for previously untested symbols in `fichero/kg`.

Focuses on pure functions / lightweight logic with fake DB objects so the
tests stay deterministic and headless.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from pathlib import Path
import sys
import types

import networkx as nx
import pandas as pd
import pytest
from pydantic import ValidationError

from fichero_server.knowledge.graph import (
    CentralityScore,
    MergeCandidate,
    build_full_cooccurrence,
    build_full_graph,
    contradiction_subgraph,
    invalidate_graph_cache,
)
from fichero_server.knowledge.ner import BaseNERProvider, ExtractedEntity, NERProvider
from fichero_server.knowledge.paragraph import (
    ParagraphCitation,
    ParagraphMarker,
    ParagraphRenderRequest,
    ParagraphRenderResponse,
    ParagraphStyle,
)
from fichero_server.knowledge.probabilistic_scorer import ThresholdDecision
from fichero_server.knowledge.pykeen_predictor import LinkPrediction, load_model, predict_for_subject
from fichero_server.knowledge.triangulation import TripleKey, TripleSupport
from fichero_server.models.knowledge import ClaimRelationType


class _FakeDatabase:
    """Small protocol-compatible fake for DB interactions in KG graph helpers."""

    def __init__(
        self,
        path: str | Path,
        *,
        query_payloads: dict[str, list[Any]],
        claim_payloads: dict[str, Any],
        signatures: dict[str, tuple[int, Any]],
    ):
        self.path = Path(path)
        self._query_payloads = query_payloads
        self._claim_payloads = claim_payloads
        self._signatures = signatures
        self.queries = 0

    def knowledge_table_signature(self, table: str) -> tuple[int, Any]:
        return self._signatures[table]

    def query(self, model: Any) -> list[Any]:
        self.queries += 1
        key = getattr(model, "__name__", str(model))
        return list(self._query_payloads.get(key, []))

    def get(self, model: Any, row_id: str) -> Any:
        return self._claim_payloads.get(row_id)


def _sample_entities() -> list[Any]:
    return [
        SimpleNamespace(id="e-1", canonical_name="Alice", entity_type="person", aliases=[]),
        SimpleNamespace(id="e-2", canonical_name="Bob", entity_type="person", aliases=["Bobby"]),
    ]


def _sample_claims() -> list[Any]:
    return [
        SimpleNamespace(
            id="c-1",
            entity_ids=["e-1", "e-2"],
            source_document_id="doc-1",
            source_page_label="1",
            metadata={"verb": "Meets", "object": "Carol"},
            epistemic_status=None,
            text="Alice meets Carol.",
            source_excerpt="Alice meets Carol",
            source_bbox=[1, 2, 3, 4],
            source_char_start=0,
            source_char_end=17,
        ),
        SimpleNamespace(
            id="c-2",
            entity_ids=["e-2"],
            source_document_id="doc-2",
            source_page_label="2",
            metadata={"verb": "Mentions", "object": "Dora"},
            epistemic_status=None,
            text="Bob mentions Dora.",
            source_excerpt="Bob mentions Dora",
            source_bbox=[1, 2, 3, 4],
            source_char_start=0,
            source_char_end=16,
        ),
    ]


def test_graph_dataclasses_expose_expected_fields():
    score = CentralityScore("e-1", "Alice", 3, 0.2, 0.3)
    merge = MergeCandidate(
        entity_a_id="e-1",
        entity_b_id="e-2",
        name_a="Alice",
        name_b="Bob",
        shared_neighbours=2,
        jaccard=0.75,
    )

    assert score.entity_id == "e-1"
    assert score.canonical_name == "Alice"
    assert merge.jaccard > 0


def test_graph_cache_build_full_graph_and_invalidate():
    db = _FakeDatabase(
        path=Path("/tmp/kg-cache-a"),
        query_payloads={
            "KnowledgeEntity": _sample_entities(),
            "KnowledgeClaim": _sample_claims(),
            "KnowledgeClaimLink": [],
        },
        claim_payloads={},
        signatures={
            "knowledgeclaims": (1, "2026-01-01T00:00:00"),
            "knowledgeentitys": (1, "2026-01-01T00:00:00"),
        },
    )

    first = build_full_graph(db)
    second = build_full_graph(db)

    assert isinstance(first, nx.MultiDiGraph)
    assert second is first
    assert db.queries == 2
    assert first.number_of_nodes() == 4
    assert first.number_of_edges() == 3

    coo = build_full_cooccurrence(db)
    assert isinstance(coo, nx.Graph)
    assert coo.number_of_edges() == 1

    invalidate_graph_cache(db)
    third = build_full_graph(db)
    assert third is not first
    assert db.queries == 6


def test_contradiction_subgraph_only_includes_contradictions():
    claim_1 = SimpleNamespace(id="c-1", text="Alice says X")
    claim_2 = SimpleNamespace(id="c-2", text="Bob says Y")
    claim_3 = SimpleNamespace(id="c-3", text="Carol says Z")

    links = [
        SimpleNamespace(
            source_claim_id="c-1",
            target_claim_id="c-2",
            relation=ClaimRelationType.contradicts,
        ),
        SimpleNamespace(
            source_claim_id="c-2",
            target_claim_id="c-3",
            relation=ClaimRelationType.supports,
        ),
    ]

    db = _FakeDatabase(
        path=Path("/tmp/kg-contradiction"),
        query_payloads={
            "KnowledgeClaimLink": links,
        },
        claim_payloads={
            "c-1": claim_1,
            "c-2": claim_2,
            "c-3": claim_3,
        },
        signatures={
            "knowledgeclaims": (1, "x"),
            "knowledgeentitys": (1, "x"),
        },
    )

    graph = contradiction_subgraph(db)

    assert set(graph.nodes) == {"c-1", "c-2"}
    assert {frozenset(edge) for edge in graph.edges} == {frozenset(("c-1", "c-2"))}
    assert "c-3" not in graph.nodes


def test_ner_provider_contract_and_abstract_base_contract():
    with pytest.raises(TypeError):
        BaseNERProvider()  # pragma: no cover - abstract base class

    class _Dummy:
        name = "dummy"
        model_name = "model"

        async def extract(self, text, language=None, state=None, llm_config=None, inputs=None):
            return [
                ExtractedEntity(
                    name="Alice",
                    type="person",
                    provider_name="dummy",
                    confidence=0.9,
                    source_offsets=(0, 5),
                )
            ]

    assert isinstance(_Dummy(), NERProvider)


def test_paragraph_models_set_defaults_and_validation():
    marker = ParagraphMarker(marker_index=2, start=12, end=13, token="[2]")
    citation = ParagraphCitation(
        marker_index=2,
        claim_id="claim-1",
        source_document_id="doc-1",
    )
    request = ParagraphRenderRequest(claim_ids=["a", "b"])
    response = ParagraphRenderResponse(style=ParagraphStyle.narrative, text="x")

    assert marker.token == "[2]"
    assert citation.source_page_label is None
    assert request.style == ParagraphStyle.narrative
    assert response.citations == []
    assert response.markers == []
    with pytest.raises(ValidationError):
        ParagraphRenderRequest(claim_ids=[], style=ParagraphStyle.list)


def test_threshold_decision_repr_and_slots():
    decision = ThresholdDecision("queue", 0.7321, "score in queue band")

    assert decision.action == "queue"
    assert decision.score == 0.7321
    assert decision.reason == "score in queue band"
    assert repr(decision) == "ThresholdDecision(queue, 0.732)"
    with pytest.raises(AttributeError):
        decision.__dict__  # dataclass with __slots__


def test_link_prediction_record_fields():
    row = LinkPrediction("s-1", "likes", "o-1", 0.82)
    assert row.subject_id == "s-1"
    assert row.score == 0.82


def test_load_model_returns_none_for_missing_artifact(tmp_path):
    db = SimpleNamespace(path=tmp_path)
    assert load_model(db) is None


def test_load_model_roundstrip_with_mocked_torch(tmp_path, monkeypatch):
    db = SimpleNamespace(path=tmp_path / "db")
    model_path = db.path.parent / "pykeen" / "trained_model.pkl"
    model_path.parent.mkdir()
    model_path.write_bytes(b"not-a-real-torch-payload")

    fake_torch = types.SimpleNamespace(load=lambda *_args, **_kwargs: {"loaded": True})
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert load_model(db) == {"loaded": True}


def test_load_model_handles_torch_exception(tmp_path, monkeypatch):
    db = SimpleNamespace(path=tmp_path / "db")
    model_path = db.path.parent / "pykeen" / "trained_model.pkl"
    model_path.parent.mkdir()
    model_path.write_bytes(b"bad")

    def _fail(*_args, **_kwargs):
        raise RuntimeError("boom")

    fake_torch = types.SimpleNamespace(load=_fail)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert load_model(db) is None


def test_predict_for_subject_requires_pykeen_predict_dependency(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pykeen", types.ModuleType("pykeen"))
    monkeypatch.setitem(sys.modules, "pykeen.predict", types.ModuleType("pykeen.predict"))

    db = SimpleNamespace(path=tmp_path)
    assert predict_for_subject(db, "s-1") == []


def test_predict_for_subject_orders_truncated_predictions(tmp_path, monkeypatch):
    db = SimpleNamespace(path=tmp_path / "pkg" / "library.db")
    (tmp_path / "pkg").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "pykeen").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "pykeen" / "training_triples").touch()

    model = object()
    # predict_for_subject resolves load_model from its own module
    # (fichero_server.knowledge.pykeen_predictor); fichero_server.knowledge.pykeen_predictor is just
    # an `import *` shim, so patching the shim name has no effect on the call.
    monkeypatch.setattr(
        "fichero_server.knowledge.pykeen_predictor.load_model",
        lambda _db: model,
    )

    class _FakeTF:
        entity_to_id = {"s-1": 0}
        relation_to_id = {"r-a": 0, "r-b": 1}

        @classmethod
        def from_path_binary(cls, path):  # pragma: no cover - signature parity only
            return cls()

    class _FakeResult:
        def __init__(self, rows):
            self.df = pd.DataFrame(rows)

    def _predict_target(model, head, relation, triples_factory):  # pragma: no cover - branch
        if relation == "r-a":
            rows = [
                {"tail_label": "x", "score": 0.2},
                {"tail_label": "y", "score": 0.9},
            ]
        else:
            rows = [
                {"tail_label": "z", "score": 0.8},
                {"tail_label": "w", "score": 0.3},
            ]
        return _FakeResult(rows)

    fake_predict_module = types.ModuleType("pykeen.predict")
    fake_predict_module.predict_target = _predict_target

    fake_triples_module = types.ModuleType("pykeen.triples")
    fake_triples_module.TriplesFactory = _FakeTF

    fake_pykeen = types.ModuleType("pykeen")
    fake_pykeen.predict = fake_predict_module
    fake_pykeen.triples = fake_triples_module

    monkeypatch.setitem(sys.modules, "pykeen", fake_pykeen)
    monkeypatch.setitem(sys.modules, "pykeen.predict", fake_predict_module)
    monkeypatch.setitem(sys.modules, "pykeen.triples", fake_triples_module)

    result = predict_for_subject(db, subject_id="s-1", top_k=3)

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0].score == 0.9
    assert result[0].predicate == "r-a"
    assert result[1].score == 0.8
    assert result[2].score == 0.3


def test_triple_support_corroboration_property():
    key = TripleKey("s-1", "like", "alice")
    low = TripleSupport(
        key=key,
        support_count=1,
        weighted_support=1.9,
        source_document_ids=("d-1",),
        claim_ids=("c-1",),
    )
    medium = TripleSupport(
        key=key,
        support_count=1,
        weighted_support=2.0,
        source_document_ids=("d-1", "d-2"),
        claim_ids=("c-1",),
    )
    high = TripleSupport(
        key=key,
        support_count=5,
        weighted_support=3.4,
        source_document_ids=("d-1", "d-2", "d-3"),
        claim_ids=("c-1",),
    )

    assert low.corroboration == "single-source"
    assert medium.corroboration == "corroborated"
    assert high.corroboration == "triangulated"
