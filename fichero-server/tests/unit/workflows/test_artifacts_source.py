"""Artifacts Source — run a step on what an earlier step WROTE.

Every workflow's source resolved to files, so a run always began at the image
and each tool decided internally what to read. Translating the REVIEWED
transcription rather than the page was therefore impossible to express
(Daniel, 2026-08-28), and every Translate preset re-transcribes first — paying
for the hard reading twice and translating a text nobody checked.
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.workflows.tools.artifacts_source import artifacts_source_tool

PRESETS = (
    pathlib.Path(__file__).resolve().parents[3]
    / "src/fichero_server/resources/default_workflows"
)


def _artifact(text, *, created_at, step_name=""):
    row = MagicMock()
    row.content = text
    row.created_at = created_at
    row.step_name = step_name
    return row


def _db(artifacts):
    db = MagicMock()
    document = MagicMock()
    document.model_dump.return_value = {"id": "doc-1", "name": "Hoja 531"}
    db.get.return_value = document
    db.query.return_value = artifacts
    return db


async def _run(db, config, doc_ids=("doc-1",)):
    with patch("fichero_server.db.db_manager.get_database", return_value=db):
        return await artifacts_source_tool(
            {},
            {"library_path": "/tmp/lib", "selected_doc_ids": list(doc_ids)},
            None,
            config,
        )


class TestArtifactsSource:
    @pytest.mark.asyncio
    async def test_latest_wins_because_a_third_review_supersedes_the_first(self):
        db = _db([
            _artifact("first pass", created_at=1),
            _artifact("final pass", created_at=3),
            _artifact("second pass", created_at=2),
        ])
        result = await _run(db, {"artifact_type": "transcription_review", "which": "latest"})

        assert result["count"] == 1
        assert result["records"][0]["text"] == "final pass"

    @pytest.mark.asyncio
    async def test_all_emits_every_pass_for_comparison(self):
        db = _db([
            _artifact("first pass", created_at=1),
            _artifact("final pass", created_at=2),
        ])
        result = await _run(db, {"artifact_type": "transcription_review", "which": "all"})
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_step_name_picks_one_pass_among_several(self):
        db = _db([
            _artifact("abbreviations", created_at=1, step_name="r1"),
            _artifact("final", created_at=2, step_name="r3"),
        ])
        result = await _run(
            db,
            {"artifact_type": "transcription_review", "which": "all", "step_name": "r1"},
        )
        assert result["count"] == 1
        assert result["records"][0]["text"] == "abbreviations"

    @pytest.mark.asyncio
    async def test_a_document_with_no_artifact_is_skipped_not_faked(self):
        # A chain that translated four of five pages must not look complete;
        # the missing page contributes nothing rather than an empty record.
        result = await _run(_db([]), {"artifact_type": "transcription_review"})
        assert result["count"] == 0
        assert result["records"] == []
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_nothing_selected_yields_nothing(self):
        result = await _run(_db([]), {}, doc_ids=())
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_empty_artifact_content_is_not_emitted_as_a_record(self):
        db = _db([_artifact("   ", created_at=1)])
        result = await _run(db, {"artifact_type": "transcription_review"})
        assert result["count"] == 0


class TestTranslateReviewedPreset:
    def test_the_preset_reads_the_review_instead_of_re_transcribing(self):
        data = json.loads(
            (PRESETS / "translate_reviewed_transcription.json").read_text()
        )
        tools = [node["tool"] for node in data["nodes"]]

        assert "artifacts_source" in tools
        # The point of the preset: no transcribe step at all.
        assert not any(tool.startswith("transcribe") for tool in tools)

        source = next(n for n in data["nodes"] if n["tool"] == "artifacts_source")
        assert source["config"]["artifact_type"] == "transcription_review"
