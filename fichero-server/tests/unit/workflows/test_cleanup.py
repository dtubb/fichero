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

from fichero_server.models.knowledge import EntityType, KnowledgeEntity
from fichero_server.workflows.tools.cleanup import (
    _apply_groups,
    _ask_llm_to_dedupe,
    _build_cleanup_prompt,
    _replace_artifact,
)


class TestRegistration:
    def test_twelve_cleanup_tools_registered(self):
        from fichero_server.workflows.registry import TOOLS

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
    """Now returns (instructions, user_prompt) so the chat() call routes
    rules to Apple Intelligence's Instructions channel and items to the
    Prompt channel (#815)."""

    def test_returns_tuple(self):
        result = _build_cleanup_prompt(_PEOPLE_CFG, ["Don Mateo"])
        assert isinstance(result, tuple) and len(result) == 2

    def test_user_prompt_includes_all_names_numbered(self):
        _, user = _build_cleanup_prompt(_PEOPLE_CFG, ["Don Mateo", "D. Mateo"])
        assert "1. Don Mateo" in user
        assert "2. D. Mateo" in user

    def test_instructions_describe_groups_json_shape(self):
        instructions, _ = _build_cleanup_prompt(_PLACES_CFG, ["Cali"])
        assert "groups" in instructions
        assert "canonical" in instructions
        assert "aliases" in instructions

    def test_instructions_use_lower_cased_display(self):
        instructions, _ = _build_cleanup_prompt(_ORGS_CFG, ["X", "Y"])
        assert "organizations" in instructions

    def test_instructions_include_per_type_duplicate_rule(self):
        instructions, _ = _build_cleanup_prompt(_PEOPLE_CFG, ["A", "B"])
        assert _PEOPLE_CFG["duplicate_rule"] in instructions


class TestAskLLMToDedupe:
    """Cleanup uses chat_structured_with_fallback (#845) — grammar-constrained
    output returns a typed _DedupResult Pydantic instance. The old
    json.loads / _strip_fences / invalid-JSON paths are gone because invalid
    JSON cannot be emitted; tests now mock the structured call directly.
    """

    @staticmethod
    def _mock_dedup(groups: list[dict[str, list[str]]]):
        """Build a mock chat_structured_with_fallback that returns a
        _DedupResult instance shaped like the LLM response."""
        from fichero_server.workflows.tools.cleanup import _DedupGroup, _DedupResult
        return AsyncMock(
            return_value=_DedupResult(
                groups=[
                    _DedupGroup(canonical=g["canonical"], aliases=g.get("aliases", []))
                    for g in groups
                ]
            )
        )

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        cfg = MagicMock()
        result = await _ask_llm_to_dedupe(_PEOPLE_CFG, [], cfg)
        assert result == []

    @pytest.mark.asyncio
    async def test_single_name_skips_llm(self):
        cfg = MagicMock()
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=AsyncMock(),
        ) as mock_call:
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["Solo"], cfg)
        mock_call.assert_not_called()
        assert result == [{"canonical": "Solo", "aliases": []}]

    @pytest.mark.asyncio
    async def test_parses_well_formed_groups(self):
        cfg = MagicMock()
        mock = self._mock_dedup([
            {
                "canonical": "Don Mateo Restrepo",
                "aliases": ["Don Mateo", "D. Mateo"],
            },
        ])
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=mock,
        ):
            result = await _ask_llm_to_dedupe(
                _PEOPLE_CFG, ["Don Mateo", "D. Mateo", "Don Mateo Restrepo"], cfg
            )
        assert result == [
            {"canonical": "Don Mateo Restrepo", "aliases": ["Don Mateo", "D. Mateo"]}
        ]

    @pytest.mark.asyncio
    async def test_backfills_missing_inputs_as_singletons(self):
        """When the LLM drops inputs (despite the schema constraint), the
        backfill pass adds them as their own single-item groups. We are
        deduplicating, not curating — every input must end up somewhere."""
        cfg = MagicMock()
        mock = self._mock_dedup([
            {"canonical": "X", "aliases": []},
        ])
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=mock,
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["X", "Y"], cfg)
        assert result == [
            {"canonical": "X", "aliases": []},
            {"canonical": "Y", "aliases": []},
        ]

    @pytest.mark.asyncio
    async def test_llm_failure_returns_identity_grouping(self):
        """LLM transport failures (network/auth/timeout) leave us without
        a dedup decision; rather than dropping all entities for that section,
        we return identity grouping (each input as its own canonical) so
        the rest of the workflow continues. Replaces the old "return []"
        which silently produced zero claims for the section (#845)."""
        cfg = MagicMock()
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=AsyncMock(side_effect=RuntimeError("transport fail")),
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["A", "B"], cfg)
        assert result == [
            {"canonical": "A", "aliases": []},
            {"canonical": "B", "aliases": []},
        ]

    @pytest.mark.asyncio
    async def test_drops_aliases_equal_to_canonical(self):
        """LLM sometimes returns the canonical name itself in the aliases
        list — produces redundant '(aka <self>)' suffixes in the inspector
        (#825). Cleanup must filter these out, casefold-equality."""
        cfg = MagicMock()
        mock = self._mock_dedup([
            {"canonical": "Alaska", "aliases": ["Alaska", "ALASKA", "Alaskan"]},
        ])
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=mock,
        ):
            result = await _ask_llm_to_dedupe(
                _PLACES_CFG, ["Alaska", "ALASKA", "Alaskan"], cfg,
            )
        # Self-aliases dropped; "Alaskan" kept (real spelling variant).
        assert result == [{"canonical": "Alaska", "aliases": ["Alaskan"]}]

    @pytest.mark.asyncio
    async def test_drops_aliases_with_only_whitespace(self):
        cfg = MagicMock()
        mock = self._mock_dedup([
            {"canonical": "Real", "aliases": ["", "   ", "Realer"]},
        ])
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=mock,
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["Real", "Realer"], cfg)
        assert result == [{"canonical": "Real", "aliases": ["Realer"]}]

    @pytest.mark.asyncio
    async def test_overflow_triggers_split_and_recurse(self):
        """When Apple Intelligence emits the typed (decoding) error
        because the prompt + schema + names list overflows the 4K
        window, _ask_llm_to_dedupe splits the names in half and
        recurses (#848). Each half succeeds; results are concatenated.
        """
        cfg = MagicMock()
        from fichero_server.workflows.tools.cleanup import _DedupGroup, _DedupResult

        call_count = {"n": 0}

        async def flaky_chat(prompt, schema, config, system=None, include_schema_in_prompt=None):
            call_count["n"] += 1
            # First call: simulate Apple's (decoding) overflow.
            if call_count["n"] == 1:
                raise RuntimeError(
                    "Apple Intelligence (decoding): truncated mid-output"
                )
            # Subsequent calls (each half): return one group per name.
            # Match the user_prompt's numbered list to extract names.
            import re
            entries = re.findall(r"\d+\. (.+)", prompt)
            return _DedupResult(
                groups=[
                    _DedupGroup(canonical=n, aliases=[]) for n in entries
                ]
            )

        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=flaky_chat,
        ):
            result = await _ask_llm_to_dedupe(
                _PEOPLE_CFG, ["A", "B", "C", "D", "E", "F"], cfg,
            )

        # 1 failed + 2 successful = 3 calls
        assert call_count["n"] == 3
        # All 6 inputs returned via the two halves
        canonicals = [g["canonical"] for g in result]
        assert sorted(canonicals) == ["A", "B", "C", "D", "E", "F"]

    @pytest.mark.asyncio
    async def test_overflow_at_max_depth_falls_through_to_identity(self):
        """Recursive split is bounded — beyond _MAX_DEDUP_DEPTH we
        fall through to identity grouping rather than recursing forever
        on a fundamentally too-big input."""
        cfg = MagicMock()
        from fichero_server.workflows.tools import cleanup as cleanup_mod

        async def always_overflow(*a, **kw):
            raise RuntimeError("Apple Intelligence (decoding): truncated")

        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=always_overflow,
        ), patch.object(cleanup_mod, "_MAX_DEDUP_DEPTH", 1):
            result = await _ask_llm_to_dedupe(
                _PEOPLE_CFG, ["A", "B", "C", "D"], cfg,
            )
        # All 4 names ended up as identity-grouping (no merges); none
        # were lost.
        canonicals = sorted(g["canonical"] for g in result)
        assert canonicals == ["A", "B", "C", "D"]

    @pytest.mark.asyncio
    async def test_drops_groups_without_canonical(self):
        """The schema constraint forces `canonical: str` (non-Optional),
        but the LLM can still emit empty strings. These get dropped and
        the orphaned inputs are backfilled as their own groups."""
        cfg = MagicMock()
        mock = self._mock_dedup([
            {"canonical": "", "aliases": ["x"]},
            {"canonical": "Real", "aliases": []},
        ])
        with patch(
            "fichero_server.workflows.tools.cleanup.chat_structured_with_fallback",
            new=mock,
        ):
            result = await _ask_llm_to_dedupe(_PEOPLE_CFG, ["A", "B"], cfg)
        # "Real" is the only valid LLM group; A and B are backfilled.
        assert result == [
            {"canonical": "Real", "aliases": []},
            {"canonical": "A", "aliases": []},
            {"canonical": "B", "aliases": []},
        ]


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
        from fichero_server.models import Artifact

        db = MagicMock()
        # A real Artifact, not a mock: the sweep now asks the curation guard
        # whether a person corrected this row (#4415 wiring), which reads the
        # row's id and marker field. A MagicMock answers every attribute, so
        # it cannot tell "unstamped machine output" from anything else — the
        # mock would pass whatever the guard did.
        prior = Artifact(
            id="prior-people-clean",
            document_id="folder-1",
            artifact_type="people_clean",
            content="stale",
        )
        db.query.side_effect = lambda model, **kwargs: (
            [prior] if model is Artifact else []
        )

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
        db.query.side_effect = lambda model, **kwargs: []
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
