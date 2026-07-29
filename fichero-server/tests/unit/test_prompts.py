"""Tests for fichero/prompts.py — the versioned prompt registry (#816)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm.prompts import (
    INSTRUMENT_SYSTEM_PROMPT,
    Prompt,
    PromptMetadata,
    PromptNotFound,
    _parse_prompt_file,
    compose_system_prompt,
    get_prompt,
    list_versions,
    load_prompt,
)


# =============================================================================
# Frontmatter parsing
# =============================================================================


class TestParsePromptFile:
    def test_full_frontmatter(self, tmp_path: Path):
        path = tmp_path / "demo_v3.md"
        path.write_text(
            "---\n"
            "version: 3\n"
            "model_target: small\n"
            "author: dtubb\n"
            "date: 2026-05-06\n"
            "changelog: shorter, role-based\n"
            "---\n"
            "Hello {name}, this is the prompt body."
        )
        prompt = _parse_prompt_file(path, tool="demo_tool")
        assert prompt.name == "demo"
        assert prompt.tool == "demo_tool"
        assert prompt.metadata.version == 3
        assert prompt.metadata.model_target == "small"
        assert prompt.metadata.author == "dtubb"
        assert prompt.metadata.date == "2026-05-06"
        assert "shorter, role-based" in prompt.metadata.changelog
        assert prompt.template == "Hello {name}, this is the prompt body."

    def test_missing_frontmatter_raises(self, tmp_path: Path):
        path = tmp_path / "broken_v1.md"
        path.write_text("Just a body, no frontmatter.")
        with pytest.raises(ValueError, match="frontmatter"):
            _parse_prompt_file(path, tool="t")

    def test_filename_must_match_v_pattern(self, tmp_path: Path):
        path = tmp_path / "no_version.md"
        path.write_text("---\nversion: 1\n---\nbody")
        with pytest.raises(ValueError, match="<name>_v<N>.md"):
            _parse_prompt_file(path, tool="t")

    def test_filename_version_must_match_frontmatter(self, tmp_path: Path):
        path = tmp_path / "demo_v2.md"
        path.write_text(
            "---\nversion: 5\n---\nbody"
        )
        with pytest.raises(ValueError, match="filename says v2 but"):
            _parse_prompt_file(path, tool="t")

    def test_unknown_frontmatter_keys_go_to_extra(self, tmp_path: Path):
        path = tmp_path / "demo_v1.md"
        path.write_text(
            "---\n"
            "version: 1\n"
            "max_tokens: 200\n"
            "experimental_flag: true\n"
            "---\n"
            "body"
        )
        prompt = _parse_prompt_file(path, tool="t")
        assert prompt.metadata.extra == {
            "max_tokens": 200,
            "experimental_flag": True,
        }


# =============================================================================
# Rendering
# =============================================================================


class TestPromptRender:
    def _make(self, body: str) -> Prompt:
        return Prompt(
            tool="t", name="n", template=body,
            metadata=PromptMetadata(version=1),
        )

    def test_substitutes_placeholders(self):
        p = self._make("Hello {name}, today is {day}.")
        assert p.render(name="Daniel", day="Tuesday") == \
            "Hello Daniel, today is Tuesday."

    def test_missing_placeholder_raises(self):
        p = self._make("Need {missing}")
        with pytest.raises(KeyError):
            p.render()


# =============================================================================
# Lookup with multiple versions
# =============================================================================


class TestLookup:
    @pytest.fixture
    def fake_dir(self, tmp_path, monkeypatch):
        # Build a fake prompts dir, point _PROMPTS_DIR + clear cache.
        from fichero_server.llm import prompts as registry
        tool_dir = tmp_path / "demo"
        tool_dir.mkdir()
        for version in (1, 2, 4):  # gap intentional
            (tool_dir / f"narrative_v{version}.md").write_text(
                f"---\nversion: {version}\n---\nv{version} body"
            )
        monkeypatch.setattr(registry, "_PROMPTS_DIR", tmp_path)
        # The lru_cache on _list_prompt_files needs busting — clear it.
        registry._list_prompt_files.cache_clear()
        return tmp_path

    def test_list_versions_sorted(self, fake_dir):
        assert list_versions("demo", "narrative") == [1, 2, 4]

    def test_get_latest_returns_highest_version(self, fake_dir):
        prompt = get_prompt("demo", "narrative")
        assert prompt.metadata.version == 4
        assert prompt.template == "v4 body"

    def test_get_pinned_version(self, fake_dir):
        prompt = get_prompt("demo", "narrative", version=2)
        assert prompt.metadata.version == 2
        assert prompt.template == "v2 body"

    def test_get_missing_version_raises(self, fake_dir):
        with pytest.raises(PromptNotFound, match="no v3"):
            get_prompt("demo", "narrative", version=3)

    def test_get_missing_tool_raises(self, fake_dir):
        with pytest.raises(PromptNotFound, match="No prompt files"):
            get_prompt("nonexistent", "anything")

    def test_load_prompt_renders_latest(self, fake_dir):
        # Add a v5 with a placeholder
        (fake_dir / "demo" / "narrative_v5.md").write_text(
            "---\nversion: 5\n---\nLang: {output_language}"
        )
        from fichero_server.llm import prompts as registry
        registry._list_prompt_files.cache_clear()
        result = load_prompt(
            "demo", "narrative", output_language="English",
        )
        assert result == "Lang: English"


# =============================================================================
# Shipped prompts
# =============================================================================


class TestShippedPrompts:
    """The repo ships a v1 catalogue narrative — the registry must
    actually find and parse it, otherwise catalogue._build_prompt()
    fails at runtime."""

    def test_catalogue_narrative_v1_loads(self):
        prompt = get_prompt("catalogue", "narrative", version=1)
        assert prompt.metadata.version == 1
        assert prompt.metadata.model_target == "small"
        assert "expert archivist" in prompt.template

    def test_catalogue_narrative_renders_with_language(self):
        rendered = load_prompt(
            "catalogue", "narrative",
            output_language="English",
        )
        assert "English" in rendered
        # No leftover {output_language} placeholder.
        assert "{output_language}" not in rendered

    def test_catalogue_narrative_latest_preserves_uncertainty_markers(self):
        rendered = load_prompt(
            "catalogue", "narrative",
            output_language="English",
        )
        assert "[ilegible]" in rendered
        assert "[uncertain]" in rendered

    def test_catalogue_build_prompt_uses_registry(self):
        from fichero_server.workflows.tools.catalogue import _build_prompt
        out = _build_prompt("Spanish")
        assert "Spanish" in out
        assert "expert archivist" in out
        assert "[ilegible]" in out


class TestInstrumentSystemPrompt:
    def test_core_doctrine_contains_non_negotiables(self):
        lowered = INSTRUMENT_SYSTEM_PROMPT.lower()
        assert "never pretend to be human" in lowered
        assert "do not interpret the sources for the user" in lowered
        assert "do not flatter, mirror, or manipulate the user" in lowered
        assert "quote or cite source fragments with provenance or anchors" in lowered
        assert "local-first and private" in lowered

    def test_role_prompt_includes_core_doctrine(self):
        prompt = compose_system_prompt(role="research")
        assert INSTRUMENT_SYSTEM_PROMPT in prompt
        assert "source discovery" in prompt

    def test_extra_instructions_are_composed_not_dropped(self):
        prompt = compose_system_prompt(
            role="agent",
            extra="Use the archive search tool before answering.",
        )
        assert INSTRUMENT_SYSTEM_PROMPT in prompt
        assert "Use the archive search tool before answering." in prompt
