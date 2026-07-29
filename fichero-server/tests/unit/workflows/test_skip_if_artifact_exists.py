"""
Tests for the skip-if-artifact-exists idempotency branch.

The behaviour under test: running a tool whose skip_if_artifact_exists is
True should NOT re-invoke the LLM/OCR when an artifact of the same type
already exists for the input document. Instead the tool returns the cached
artifact's content as if it had just produced it.

We patch the DB to isolate the pure lookup logic in find_existing_artifact,
and check the LLMToolConfig field default.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fichero_server.workflows.tools.llm_base import (
    ArtifactLookupError,
    LLMToolConfig,
    find_existing_artifact,
)


class TestLLMToolConfigDefault:
    def test_skip_flag_defaults_true(self):
        cfg = LLMToolConfig(artifact_type="transcription")
        assert cfg.skip_if_artifact_exists is True

    def test_skip_flag_can_be_disabled(self):
        cfg = LLMToolConfig(artifact_type="transcription", skip_if_artifact_exists=False)
        assert cfg.skip_if_artifact_exists is False


class TestFindExistingArtifact:
    def _patch_db(self, db_mock: MagicMock):
        return patch(
            "fichero_server.db.db_manager.get_database",
            return_value=db_mock,
        )

    def test_returns_none_without_library(self):
        result = find_existing_artifact(
            document_id="d1",
            file_path=None,
            artifact_type="transcription",
            library_path="",
        )
        assert result is None

    def test_returns_none_without_artifact_type(self):
        result = find_existing_artifact(
            document_id="d1",
            file_path=None,
            artifact_type="",
            library_path="/tmp/lib.fichero",
        )
        assert result is None

    def test_returns_artifact_when_document_id_resolves(self):
        doc = MagicMock(id="d1")
        artifact = MagicMock(id="a1", created_at=1)
        db = MagicMock()
        db.get.return_value = doc
        db.query.return_value = [artifact]

        with self._patch_db(db):
            result = find_existing_artifact(
                document_id="d1",
                file_path=None,
                artifact_type="transcription",
                library_path="/tmp/lib.fichero",
            )

        assert result is artifact
        # Confirms the lookup is scoped to (document_id, artifact_type).
        db.query.assert_called_once()
        _args, kwargs = db.query.call_args
        assert kwargs["document_id"] == "d1"
        assert kwargs["artifact_type"] == "transcription"

    def test_no_file_path_fallback_when_explicit_document_id_misses(self):
        # #2430: an explicit document_id is trusted as the dedup key — we query
        # artifacts by it directly and must NOT fall back to a file_path document
        # lookup when the id is given. For a page child the path resolves to the
        # PARENT PDF, whose artifacts would wrongly dedup (skip) the page's. With
        # no artifacts under the id, return None so the caller creates, not skips.
        db = MagicMock()
        db.get.return_value = None     # doc row not visible / not fetched
        db.query.return_value = []     # no existing artifacts for this id

        with self._patch_db(db):
            result = find_existing_artifact(
                document_id="missing",
                file_path="/library/f.pdf",
                artifact_type="transcription",
                library_path="/tmp/lib.fichero",
            )
        assert result is None
        # Only the artifact query ran — never a path-based document fallback.
        for call in db.query.call_args_list:
            assert "path" not in call.kwargs

    def test_returns_most_recent_when_multiple_artifacts_exist(self):
        doc = MagicMock(id="d1")
        older = MagicMock(id="a-old", created_at=1)
        newer = MagicMock(id="a-new", created_at=2)
        db = MagicMock()
        db.get.return_value = doc
        db.query.return_value = [older, newer]

        with self._patch_db(db):
            result = find_existing_artifact(
                document_id="d1",
                file_path=None,
                artifact_type="transcription",
                library_path="/tmp/lib.fichero",
            )
        assert result is newer

    def test_returns_none_when_no_artifact_found(self):
        doc = MagicMock(id="d1")
        db = MagicMock()
        db.get.return_value = doc
        db.query.return_value = []

        with self._patch_db(db):
            result = find_existing_artifact(
                document_id="d1",
                file_path=None,
                artifact_type="transcription",
                library_path="/tmp/lib.fichero",
            )
        assert result is None

    def test_db_error_raises_not_silent_miss(self):
        # #2511: a FAILED lookup must NOT be reported as a clean cache miss
        # (return None). Returning None here would silently re-run the full
        # paid vision/LLM call while hiding the fault. The lookup must surface
        # a distinct ArtifactLookupError so callers can log "could not check
        # cache" and decide to re-run, never pretend-miss. (This replaces the
        # old test that asserted the buggy swallow-and-return-None behavior.)
        db = MagicMock()
        db.query.side_effect = RuntimeError("db offline")

        with self._patch_db(db):
            with pytest.raises(ArtifactLookupError):
                find_existing_artifact(
                    document_id="d1",
                    file_path=None,
                    artifact_type="transcription",
                    library_path="/tmp/lib.fichero",
                )
