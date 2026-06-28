"""Unit tests for fichero.cli.formatters (#1982 — python/cli coverage).

The render_* helpers are pure functions over dicts / Pydantic models — no HTTP,
no backend. They drive every `fichero` CLI line, so their human + --json output
and missing-field handling are worth pinning.
"""

from __future__ import annotations

import json

from fichero.cli.formatters import (
    render,
    render_claim,
    render_document,
    render_entity,
    render_top_entity,
)


class TestRenderEntity:
    def test_human_aligns_name_type_description(self):
        out = render_entity(
            {
                "canonical_name": "Bogotá",
                "entity_type": "location",
                "description": "Capital city",
            }
        )
        assert "Bogotá" in out
        assert "location" in out
        assert "Capital city" in out

    def test_missing_fields_show_placeholder(self):
        out = render_entity({})
        assert "(missing)" in out

    def test_long_description_truncated_with_ellipsis(self):
        out = render_entity(
            {"canonical_name": "X", "entity_type": "t", "description": "d" * 80}
        )
        assert "..." in out
        # 50-char cap + ellipsis, never the full 80.
        assert "d" * 80 not in out

    def test_json_mode_is_valid_json_roundtrip(self):
        data = {"canonical_name": "Lima", "entity_type": "location"}
        out = render_entity(data, as_json=True)
        assert json.loads(out)["canonical_name"] == "Lima"


class TestRenderClaim:
    def test_human_renders_subject_predicate_object_and_source(self):
        out = render_claim(
            {
                "subject_canonical": "Alfonso",
                "predicate_verb": "owned",
                "object_phrase": "the mill",
                "source_document_id": "doc-7",
            }
        )
        assert "Alfonso" in out
        assert "→" in out
        assert "owned" in out
        assert "the mill" in out
        assert "doc-7" in out

    def test_missing_fields_placeholder(self):
        out = render_claim({})
        assert "(missing)" in out

    def test_json_mode(self):
        out = render_claim({"subject_canonical": "A"}, as_json=True)
        assert json.loads(out)["subject_canonical"] == "A"


class TestRenderDocument:
    def test_human_prefers_filename_then_name(self):
        assert "letter.txt" in render_document(
            {"filename": "letter.txt", "doc_type": "file"}
        )
        # Falls back to name when filename absent.
        assert "Folder One" in render_document(
            {"name": "Folder One", "doc_type": "folder"}
        )

    def test_doc_type_and_truncated_description(self):
        out = render_document(
            {"filename": "f", "doc_type": "file", "description": "z" * 80}
        )
        assert "[file]" in out
        assert "..." in out

    def test_json_mode(self):
        out = render_document({"filename": "f.txt"}, as_json=True)
        assert json.loads(out)["filename"] == "f.txt"


class TestRenderDispatch:
    """render() routes to the specialized formatter by key signature."""

    def test_entity_dispatch(self):
        out = render({"canonical_name": "Cali", "entity_type": "location"})
        assert "Cali" in out

    def test_claim_dispatch(self):
        out = render({"subject_canonical": "A", "predicate_verb": "is"})
        assert "→" in out

    def test_document_dispatch(self):
        out = render({"filename": "a.txt", "doc_type": "file"})
        assert "a.txt" in out

    def test_envelope_list_unwrapped(self):
        out = render({"entities": [{"id": "e1", "canonical_name": "Uno"}]})
        assert "entities (1)" in out
        assert "Uno" in out

    def test_empty_list_is_marked(self):
        assert render([]) == "(empty)"

    def test_none_is_no_data(self):
        assert render(None) == "(no data)"


def test_render_top_entity_columns():
    out = render_top_entity({"name": "Marshall", "kind": "person", "claim_count": 12})
    assert "Marshall" in out
    assert "person" in out
    assert "12" in out
