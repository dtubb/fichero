"""Unit tests for per-section catalogue extractors."""

from __future__ import annotations

import json

import pytest

from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.tools.extractors import (
    _SECTIONS,
    _build_section_prompt,
    _render_section_markdown,
    _strip_fences,
)


EXTRACTOR_NAMES = [
    "people_extract",
    "places_extract",
    "organizations_extract",
    "dates_extract",
    "rivers_extract",
    "events_extract",
    "mines_extract",
    "properties_extract",
    "legal_references_extract",
    "keywords_extract",
]


class TestRegistration:
    @pytest.mark.parametrize("name", EXTRACTOR_NAMES)
    def test_tool_registered(self, name):
        assert get_tool(name) is not None, f"{name} not registered"

    @pytest.mark.parametrize("name", EXTRACTOR_NAMES)
    def test_metadata_complete(self, name):
        d = get_tool_def(name)
        assert d is not None
        assert d.display_name.startswith("Extract ")
        assert d.category == "llm"
        assert d.uses_llm is True
        assert any(p.id == "text" for p in d.input_ports)


class TestPromptBuilding:
    def test_prompt_contains_language(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        prompt = _build_section_prompt(section, "Portuguese")
        assert "Portuguese" in prompt
        assert "people" in prompt

    def test_prompt_substitutes_lang_placeholder_in_schema(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        prompt = _build_section_prompt(section, "English")
        # __LANG__ in item_shape gets replaced before embedding in prompt
        assert "__LANG__" not in prompt
        assert "English" in prompt

    def test_keywords_uses_flat_array_schema(self):
        section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        prompt = _build_section_prompt(section, "Spanish")
        # Keywords is a flat array of strings, not objects
        assert '"keywords": ["keyword"]' in prompt


class TestStripFences:
    def test_plain_json_untouched(self):
        assert _strip_fences('{"x": 1}') == '{"x": 1}'

    def test_strips_json_fence(self):
        raw = '```json\n{"x": 1}\n```'
        assert json.loads(_strip_fences(raw)) == {"x": 1}

    def test_strips_plain_fence(self):
        raw = '```\n{"x": 1}\n```'
        assert json.loads(_strip_fences(raw)) == {"x": 1}

    def test_leading_whitespace(self):
        raw = '   ```json\n{"x": 1}\n```'
        assert json.loads(_strip_fences(raw)) == {"x": 1}


class TestArtifactContentRendering:
    """Artifact `content` is the JSON dump of items — the structured form
    is the source of truth (also stored in `data["items"]`). Markdown
    pretty-printing was lossy and lied about what we have."""

    def test_empty_items_yields_empty_array_json(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        assert _render_section_markdown(section, []) == "[]"

    def test_keywords_serialise_as_json_array(self):
        section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        content = _render_section_markdown(section, ["café", "río", "mina"])
        parsed = json.loads(content)
        assert parsed == ["café", "río", "mina"]

    def test_people_serialise_as_list_of_dicts(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        items = [
            {"name": "Leandro", "context": "alcalde local"},
            {"name": "Juan", "context": "testigo"},
        ]
        content = _render_section_markdown(section, items)
        parsed = json.loads(content)
        assert parsed == items

    def test_dates_round_trip_normalized_field(self):
        section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
        items = [{
            "date": "12 de mayo",
            "date_normalized": "1890-05-12",
            "context": "firma",
        }]
        parsed = json.loads(_render_section_markdown(section, items))
        assert parsed[0]["date_normalized"] == "1890-05-12"

    def test_events_round_trip_event_key(self):
        section = next(s for s in _SECTIONS if s["name"] == "events_extract")
        items = [{"event": "reunión", "context": "en plaza principal"}]
        parsed = json.loads(_render_section_markdown(section, items))
        assert parsed[0]["event"] == "reunión"

    def test_preserves_unicode_without_escapes(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        items = [{"name": "María José", "context": "testigo"}]
        content = _render_section_markdown(section, items)
        # ensure_ascii=False keeps the original spelling readable.
        assert "María José" in content


class TestSectionConfig:
    def test_all_sections_defined(self):
        names = {s["name"] for s in _SECTIONS}
        assert names == set(EXTRACTOR_NAMES)

    def test_each_section_has_required_fields(self):
        for section in _SECTIONS:
            for key in ("name", "display", "artifact", "icon", "color",
                        "schema_key", "item_shape", "instruction"):
                assert key in section, f"{section.get('name')} missing {key}"

    def test_artifact_types_match_existing(self):
        # Artifact types must match what DocumentInspectorArtifactsTab renders.
        known = {"people", "places", "organizations", "dates", "rivers",
                 "events", "mines", "properties", "legal_references", "keywords"}
        for section in _SECTIONS:
            assert section["artifact"] in known
