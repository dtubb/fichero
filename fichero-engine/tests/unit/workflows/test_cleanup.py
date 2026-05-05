"""Unit tests for the per-section cleanup tools (#803, #804).

Covers:
  - 12 tools register (6 page + 6 folder)
  - Prompt construction includes the names + asks for groups JSON
  - LLM-mocked dedup parses {groups: [...]} output
  - JSON parse failure → empty groups (graceful)
  - _apply_groups merges entities idempotently
  - _replace_artifact deletes prior + saves fresh
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero.knowledge_models import EntityType, KnowledgeEntity
from fichero.workflows.tools.cleanup import (
    _apply_groups,
    _ask_llm_to_dedupe,
    _build_cleanup_prompt,
    _replace_artifact,
)


class TestRegistration:
    def test_twelve_cleanup_tools_registered(self):
        from fichero.workflows.registry import TOOLS

        page_tools = sorted(n for n in TOOLS if n.endswith("_page_cleanup"))
        folder_tools = sorted(n for n in TOOLS if n.endswith("_folder_cleanup"))
        assert len(page_tools) == 6
        assert len(folder_tools) == 6
        # Spot-check expected names
        assert "people_page_cleanup" in page_tools
        assert "places_folder_cleanup" in folder_tools


_PEOPLE_CFG = {
    "key": "people",
    "display": "People",
    "noun": "person",
    "duplicate_rule": "Two entries refer to the same person if names match.",
}
_PLACES_CFG = {
    "key": "places",
    "display": "Places",
    "noun": "place",
    "duplicate_rule": "Two entries refer to the same place if spelling variants.",
}
_ORGS_CFG = {
    "key": "organizations",
    "display": "Organizations",
    "noun": "organisation",
    "duplicate_rule": "Two entries refer to the same organisation if abbreviations.",
}


class TestBuildCleanupPrompt:
    def test_includes_all_names_numbered(self):
        prompt = _build_cleanup_prompt(_PEOPLE_CFG, ["Don Mateo", "D. Mateo"])
        assert "1. Don Mateo" in prompt
        assert "2. D. Mateo" in prompt

    def test_asks_for_groups_json_shape(self):
        prompt = _build_cleanup_prompt(_PLACES_CFG, ["Cali"])
        assert "groups" in prompt
        assert "canonical" in prompt
        assert "aliases" in prompt

    def test_lower_cased_display_in_body(self):
        prompt = _build_cleanup_prompt(_ORGS_CFG, ["X", "Y"])
        # type_cfg["display"].lower() = "organizations"
        assert "organizations" in prompt

    def test_includes_per_type_duplicate_rule(self):
        prompt = _build_cleanup_prompt(_PEOPLE_CFG, ["A", "B"])
        assert _PEOPLE_CFG["duplicate_rule"] in prompt


class TestAskLLMToDedupe:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        cfg = MagicMock()
        result = await _ask_llm_to_dedupe(_PEOPLE_CFG, [], cfg)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_name_skips_llm(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(),
        ) as mock_chat:
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["Solo"], cfg)
        mock_chat.assert_not_called()
        assert result == [{"canonical": "Solo", "aliases": []}]

    @pytest.mark.asyncio
    async def test_parses_well_formed_groups(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(
                return_value=(
                    '{"groups": ['
                    '{"canonical": "Don Mateo Restrepo", "aliases": ["Don Mateo", "D. Mateo"]}'
                    ']}'
                )
            ),
        ):
            result = await _ask_llm_to_dedupe(
                _PEOPLE_CFG, ["Don Mateo", "D. Mateo", "Don Mateo Restrepo"], cfg
            )
        assert result == [
            {"canonical": "Don Mateo Restrepo", "aliases": ["Don Mateo", "D. Mateo"]}
        ]

    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        cfg = MagicMock()
        fenced = '```json\n{"groups":[{"canonical":"X","aliases":[]}]}\n```'
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(return_value=fenced),
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["X", "Y"], cfg)
        assert result == [{"canonical": "X", "aliases": []}]

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(return_value="not json"),
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["A", "B"], cfg)
        assert result == []

    @pytest.mark.asyncio
    async def test_chat_failure_returns_empty(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(side_effect=RuntimeError("oom")),
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["A", "B"], cfg)
        assert result == []

    @pytest.mark.asyncio
    async def test_drops_groups_without_canonical(self):
        cfg = MagicMock()
        with patch(
            "fichero.workflows.tools.cleanup.chat",
            new=AsyncMock(
                return_value=(
                    '{"groups": ['
                    '{"canonical": "", "aliases": ["x"]}, '
                    '{"canonical": "Real", "aliases": []}'
                    ']}'
                )
            ),
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["A", "B"], cfg)
        assert result == [{"canonical": "Real", "aliases": []}]


class TestApplyGroups:
    def _make(self, name: str, eid: str = None) -> KnowledgeEntity:
        e = KnowledgeEntity(canonical_name=name, entity_type=EntityType.person)
        if eid:
            e.id = eid
        return e

    def test_no_groups_returns_zero(self):
        db = MagicMock()
        ents = [self._make("A"), self._make("B")]
        assert _apply_groups(db, ents, []) == 0
        db.save.assert_not_called()

    def test_merges_aliases_into_canonical(self):
        db = MagicMock()
        canonical = self._make("Don Mateo Restrepo", eid="e-canon")
        absorbed1 = self._make("Don Mateo", eid="e-1")
        absorbed2 = self._make("D. Mateo", eid="e-2")
        ents = [canonical, absorbed1, absorbed2]
        groups = [{"canonical": "Don Mateo Restrepo", "aliases": ["Don Mateo", "D. Mateo"]}]

        merged = _apply_groups(db, ents, groups)

        assert merged == 2
        assert absorbed1.merged_into_id == "e-canon"
        assert absorbed2.merged_into_id == "e-canon"
        assert "Don Mateo" in canonical.aliases
        assert "D. Mateo" in canonical.aliases

    def test_idempotent_second_run(self):
        db = MagicMock()
        canonical = self._make("Real", eid="c")
        absorbed = self._make("Variant", eid="a")
        absorbed.merged_into_id = "c"
        canonical.aliases = ["Variant"]
        groups = [{"canonical": "Real", "aliases": ["Variant"]}]

        merged = _apply_groups(db, [canonical, absorbed], groups)

        # Already merged + alias already present → nothing to save
        assert merged == 0
        assert canonical.aliases == ["Variant"]

    def test_skips_unknown_canonical(self):
        db = MagicMock()
        ents = [self._make("A"), self._make("B")]
        # Group references a canonical we don't have in the entities list
        groups = [{"canonical": "Ghost", "aliases": ["A"]}]
        assert _apply_groups(db, ents, groups) == 0

    def test_skips_alias_equal_to_canonical(self):
        db = MagicMock()
        canonical = self._make("Same", eid="x")
        groups = [{"canonical": "Same", "aliases": ["Same"]}]
        assert _apply_groups(db, [canonical], groups) == 0


class TestReplaceArtifact:
    def test_deletes_prior_then_saves_new(self):
        from fichero.models import Artifact

        db = MagicMock()
        prior = MagicMock(spec=Artifact)
        db.query.return_value = [prior]

        _replace_artifact(
            db,
            container_id="folder-1",
            artifact_type="people_clean",
            groups=[{"canonical": "X", "aliases": []}],
            provider="apple",
            model="apple-intelligence",
        )

        db.delete.assert_called_once_with(prior)
        # save called with an Artifact carrying the groups payload + content
        saved = db.save.call_args.args[0]
        assert saved.artifact_type == "people_clean"
        assert saved.data == {"groups": [{"canonical": "X", "aliases": []}]}
        assert saved.content == "X"
        assert saved.provider == "apple"
        assert saved.model == "apple-intelligence"

    def test_handles_no_prior_artifacts(self):
        db = MagicMock()
        db.query.return_value = []
        _replace_artifact(
            db,
            container_id="f",
            artifact_type="places_clean",
            groups=[{"canonical": "Cali", "aliases": []}],
            provider=None,
            model=None,
        )
        db.delete.assert_not_called()
        assert db.save.call_count == 1
