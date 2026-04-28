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
        assert "personas_clave" in prompt

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
        assert '"palabras_clave": ["keyword"]' in prompt


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


class TestMarkdownRendering:
    def test_empty_items_shows_placeholder(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        md = _render_section_markdown(section, [])
        assert "No entries found" in md

    def test_keywords_join_with_middot(self):
        section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        md = _render_section_markdown(section, ["café", "río", "mina"])
        assert "café · río · mina" in md

    def test_people_table_format(self):
        section = next(s for s in _SECTIONS if s["name"] == "people_extract")
        items = [
            {"nombre": "Leandro", "contexto": "alcalde local"},
            {"nombre": "Juan", "contexto": "testigo"},
        ]
        md = _render_section_markdown(section, items)
        assert "**Leandro**" in md
        assert "alcalde local" in md
        assert "**Juan**" in md

    def test_dates_prefers_normalized(self):
        section = next(s for s in _SECTIONS if s["name"] == "dates_extract")
        items = [
            {"fecha": "12 de mayo", "fecha_normalizada": "1890-05-12", "contexto": "firma"},
        ]
        md = _render_section_markdown(section, items)
        assert "**1890-05-12**" in md

    def test_events_uses_evento_key(self):
        section = next(s for s in _SECTIONS if s["name"] == "events_extract")
        items = [{"evento": "reunión", "contexto": "en plaza principal"}]
        md = _render_section_markdown(section, items)
        assert "**reunión**" in md


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
