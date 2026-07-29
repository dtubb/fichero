"""Unit tests for the aggregate tool."""

from __future__ import annotations

import json

import pytest

from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.aggregate import _aggregate, _coerce_records, aggregate


class TestRegistration:
    def test_tool_registered(self):
        assert get_tool("aggregate") is not None

    def test_metadata(self):
        d = get_tool_def("aggregate")
        assert d is not None
        assert d.display_name == "Aggregate"
        assert d.category == "transform"
        assert d.icon == "arrow.triangle.merge"
        # Output port named "text" is critical — downstream LLM nodes read
        # it by convention.
        assert any(p.id == "text" and p.port_type == "output" for p in d.output_ports)
        assert any(p.id == "records" and p.port_type == "output" for p in d.output_ports)
        assert any(p.id == "count" and p.port_type == "output" for p in d.output_ports)


class TestCoerceRecords:
    def test_empty(self):
        assert _coerce_records({}) == []
        assert _coerce_records({"text": None}) == []

    def test_single_string(self):
        recs = _coerce_records({"text": "hello"})
        assert len(recs) == 1
        assert recs[0]["text"] == "hello"
        assert recs[0]["doc_name"] == "item-1"

    def test_list_with_docs(self):
        recs = _coerce_records({
            "text": ["a", "b"],
            "documents": [{"id": "d1", "name": "A.jpg"}, {"id": "d2", "name": "B.jpg"}],
        })
        assert len(recs) == 2
        assert recs[0]["doc_id"] == "d1"
        assert recs[1]["doc_name"] == "B.jpg"

    def test_more_texts_than_docs(self):
        recs = _coerce_records({"text": ["a", "b", "c"], "documents": [{"name": "A"}]})
        assert len(recs) == 3
        assert recs[0]["doc_name"] == "A"
        assert recs[1]["doc_name"] == "item-2"
        assert recs[2]["doc_name"] == "item-3"


class TestAggregateModes:
    records = [
        {"index": 0, "doc_id": "1", "doc_name": "A", "text": "alpha"},
        {"index": 1, "doc_id": "2", "doc_name": "B", "text": "beta"},
    ]

    def test_concat_joins_with_separator(self):
        out = _aggregate(self.records, mode="concat", separator=" | ", pretty=False)
        assert out["text"] == "alpha | beta"
        assert out["count"] == 2

    def test_list_mode_preserves_text(self):
        out = _aggregate(self.records, mode="list", separator="\n", pretty=False)
        assert out["text"] == "alpha\nbeta"
        assert len(out["records"]) == 2

    def test_json_array_emits_valid_json(self):
        out = _aggregate(self.records, mode="json_array", separator="", pretty=False)
        payload = json.loads(out["text"])
        assert isinstance(payload, list)
        assert payload[0]["doc_name"] == "A"
        assert payload[1]["text"] == "beta"

    def test_group_by_document_keys_by_doc_id(self):
        out = _aggregate(self.records, mode="group_by_document", separator="", pretty=False)
        grouped = json.loads(out["text"])
        assert grouped == {"1": "alpha", "2": "beta"}

    def test_group_by_document_concatenates_duplicates(self):
        recs = [
            {"index": 0, "doc_id": "d1", "doc_name": "A", "text": "line1"},
            {"index": 1, "doc_id": "d1", "doc_name": "A", "text": "line2"},
        ]
        out = _aggregate(recs, mode="group_by_document", separator="", pretty=False)
        grouped = json.loads(out["text"])
        assert grouped == {"d1": "line1\nline2"}

    def test_unknown_mode_falls_back_to_concat(self):
        out = _aggregate(self.records, mode="invalid_mode", separator=":", pretty=False)
        assert out["text"] == "alpha:beta"

    def test_empty_records_returns_empty(self):
        out = _aggregate([], mode="concat", separator="|", pretty=False)
        assert out["text"] == ""
        assert out["count"] == 0


class TestAggregateIntegration:
    @pytest.mark.asyncio
    async def test_default_concat_mode(self):
        from fichero_server.llm import LLMConfig

        inputs = {
            "text": ["one", "two", "three"],
            "documents": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            "_config": {"mode": "concat", "separator": ", "},
        }
        llm = LLMConfig(provider="", model="")
        result = await aggregate(inputs, state={}, llm_config=llm)
        assert result["text"] == "one, two, three"
        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_empty_upstream(self):
        from fichero_server.llm import LLMConfig

        result = await aggregate({"text": None}, state={}, llm_config=LLMConfig(provider="", model=""))
        assert result["text"] == ""
        assert result["count"] == 0
