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
    "citation_usage_extract",
    "hermeneutics_extract",
    "keywords_extract",
    "quotes_extract",
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

    def test_citation_usage_prompt_requests_body_usage_fields(self):
        section = next(s for s in _SECTIONS if s["name"] == "citation_usage_extract")
        prompt = _build_section_prompt(section, "English")
        assert "citation_usages" in prompt
        assert "marker" in prompt
        assert "stance" in prompt
        assert "claim_text" in prompt


class TestEntityTypeDisambiguation:
    """#1009: 'agricultural zones' was typed Concept (should be Location)
    and 'accident' Concept (should be Event). Root cause: extract_all gives
    the LLM six parallel lists with no per-item type field, and `keywords`
    (→ concept) was a catch-all with no exclusion rule. These tests guard
    the disambiguation guidance in the shared instruction strings."""

    def test_places_instruction_covers_land_use_categories(self):
        section = next(s for s in _SECTIONS if s["name"] == "places_extract")
        instr = section["instruction"].lower()
        assert "agricultural zones" in instr
        assert "categor" in instr  # categories / category

    def test_events_instruction_covers_unnamed_occurrences(self):
        section = next(s for s in _SECTIONS if s["name"] == "events_extract")
        instr = section["instruction"].lower()
        assert "accident" in instr
        assert "occurrence" in instr

    def test_keywords_instruction_excludes_concrete_entities(self):
        section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        instr = section["instruction"].lower()
        # Must explicitly steer places/events away from the concept bucket.
        assert "do not put places, events" in instr
        assert "agricultural zones" in instr
        assert "accident" in instr

    def test_extract_all_propagates_disambiguation_guidance(self):
        """extract_all builds its system prompt from the same _SECTIONS
        instruction strings — the fix must reach the combined call too."""
        from fichero.workflows.tools.extract_all import _build_instructions

        instructions = _build_instructions("English").lower()
        assert "agricultural zones" in instructions
        assert "accident" in instructions
        assert "do not put places, events" in instructions


class TestKeywordOverExtraction:
    """#1051: keyword extractor dumped 18 generic keywords for one
    paragraph. The instruction must carry a salience bar + count
    guidance, and the schema must cap a runaway model."""

    def test_keywords_instruction_has_salience_bar(self):
        section = next(s for s in _SECTIONS if s["name"] == "keywords_extract")
        instr = section["instruction"].lower()
        assert "salient" in instr
        assert "5-8" in instr
        # The old "no minimum count, no padding" phrasing imposed no ceiling.
        assert "no minimum" not in instr

    def test_keyword_salience_bar_reaches_extract_all(self):
        from fichero.workflows.tools.extract_all import _build_instructions

        instructions = _build_instructions("English").lower()
        assert "salient" in instructions
        assert "5-8" in instructions

    def test_runaway_keyword_list_is_capped(self):
        from fichero.workflows.tools.extractors import (
            _KEYWORDS_MAX,
            _KeywordsResult,
        )

        runaway = [f"kw{i}" for i in range(40)]
        result = _KeywordsResult(items=runaway)
        assert len(result.items) == _KEYWORDS_MAX
        # Keeps the first N — instruction asks for most-salient-first.
        assert result.items == runaway[:_KEYWORDS_MAX]

    def test_normal_keyword_list_untouched(self):
        from fichero.workflows.tools.extractors import _KeywordsResult

        normal = ["artisanal mining", "subsistence livelihood", "the good life"]
        result = _KeywordsResult(items=normal)
        assert result.items == normal


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
        # Artifact types must match what the Knowledge inspector (EntityKindRow) renders.
        known = {"people", "places", "organizations", "dates", "rivers",
                 "events", "mines", "properties", "legal_references",
                 "citation_usages", "hermeneutics", "keywords", "quotes"}
        for section in _SECTIONS:
            assert section["artifact"] in known
