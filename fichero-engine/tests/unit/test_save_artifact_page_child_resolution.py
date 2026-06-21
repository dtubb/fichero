"""
#2430 (reopened): save_artifact file_path fallback silently routes to parent PDF.

Root cause NOT covered by test_per_page_artifact_placement.py:
  That test mocks save_artifact at the vision_base import level, so it only
  verifies the *call site* passes document_id=page_child_id.  It never
  exercises the *interior* of save_artifact where document resolution happens.

Real broken path (before this fix):
  save_artifact(document_id="page-child-id", file_path="/lib/scan.pdf")
    → db.get(Document, "page-child-id") → None  (any transient/env reason)
    → fallback: find_document_by_path(db, Document, "/lib/scan.pdf")
                → returns PARENT PDF document
    → Artifact(document_id=parent_pdf.id, ...)  ← wrong!
    → doc.page_content = content on parent PDF ← wrong!

Fix (llm_base.py): if document_id was supplied, skip the file_path fallback
entirely — an explicit id that fails to resolve must not silently reroute.

find_existing_artifact has the same pattern; fixing both prevents a stale
parent-level cached artifact from masking a fresh per-page run.

NOTE: db_manager is imported INSIDE save_artifact / find_existing_artifact via
    `from fichero.db import db_manager`
so the correct patch target is "fichero.db.db_manager", not the llm_base module.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _make_document(doc_id: str, path: str | None = None, page_content: str | None = None):
    from fichero.models import Document, DocType, Status
    return Document(
        id=doc_id,
        name="doc",
        doc_type=DocType.file,
        path=path,
        page_content=page_content,
        status=Status.pending,
        metadata={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_llm_config():
    from fichero.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


def _make_tool_config(*, update_page_content=True):
    from fichero.workflows.tools.vision_base import VisionToolConfig
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=update_page_content,
        trigger_embedding=False,
        supports_apple_vision=False,
        skip_if_artifact_exists=False,
    )


# ---------------------------------------------------------------------------
# Tests for save_artifact internal document resolution
# ---------------------------------------------------------------------------

class TestSaveArtifactPageChildResolution:
    """
    Exercises the REAL save_artifact (not mocked) to verify document resolution
    when document_id=page_child_id + file_path=parent_pdf_path are both given.

    This is the path that test_per_page_artifact_placement.py misses because
    it replaces save_artifact with a mock that captures arguments but never
    executes the db.get → fallback logic inside it.
    """

    @pytest.mark.asyncio
    async def test_artifact_lands_on_page_child_when_db_get_succeeds(self, tmp_path):
        """
        Happy path: db.get returns the page child → artifact on page child.

        Verifies the normal case works before checking the failure mode.
        """
        page_child = _make_document("page-child-id", path=None)

        saved_artifacts: list = []

        mock_db = MagicMock()
        mock_db.get.return_value = page_child          # db.get finds the page child ✓
        mock_db.save.side_effect = saved_artifacts.append

        from fichero.workflows.tools.llm_base import save_artifact

        # db_manager is imported inside save_artifact; patch at the source module.
        with patch("fichero.db.db_manager") as mgr:
            mgr.get_database.return_value = mock_db
            await save_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",          # parent PDF path — must NOT be used
                content="Page 1 transcription.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
            )

        assert saved_artifacts, "save_artifact must save something"
        artifact = saved_artifacts[0]
        assert artifact.document_id == "page-child-id", (
            f"Artifact must go to page child, got: {artifact.document_id}"
        )

    @pytest.mark.asyncio
    async def test_artifact_not_saved_to_parent_when_db_get_returns_none(self, tmp_path):
        """
        #2430 regression path: db.get returns None for page_child_id.

        BEFORE fix: file_path fallback resolves to parent PDF →
            Artifact(document_id="parent-pdf-id") ← silently wrong
        AFTER fix:  file_path fallback is skipped when document_id was given →
            save_artifact returns None (no artifact saved)

        This test FAILS on unfixed code (artifact.document_id == "parent-pdf-id")
        and PASSES after the fix (no artifact saved at all).
        """
        parent_pdf = _make_document("parent-pdf-id", path="/lib/scan.pdf")

        saved_artifacts: list = []

        mock_db = MagicMock()
        # db.get returns None — simulates the condition that triggers the bug
        mock_db.get.return_value = None
        mock_db.save.side_effect = saved_artifacts.append

        from fichero.workflows.tools.llm_base import save_artifact

        with patch("fichero.db.db_manager") as mgr, \
             patch(
                 "fichero.workflows.tools.llm_base.find_document_by_path",
                 return_value=parent_pdf,
             ):
            mgr.get_database.return_value = mock_db
            result = await save_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                content="Page 1 transcription.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
            )

        # After fix: no artifact saved because document_id was given but not found
        assert result is None, (
            "save_artifact must return None when document_id given but not found in DB"
        )
        wrong_ids = [a.document_id for a in saved_artifacts if hasattr(a, "document_id")]
        assert "parent-pdf-id" not in wrong_ids, (
            f"#2430: save_artifact must NOT fall back to parent PDF "
            f"when document_id was explicitly provided but not found. "
            f"Got artifact document_ids: {wrong_ids}"
        )

    @pytest.mark.asyncio
    async def test_artifact_saved_via_file_path_when_no_document_id(self, tmp_path):
        """
        Legitimate file_path fallback: no document_id → file_path lookup is valid.

        This is the pre-per-page-fan-out mode (single non-split file). Must
        still work after the fix so we don't regress callers that pass
        document_id=None.
        """
        parent_pdf = _make_document("parent-pdf-id", path="/lib/book.pdf")

        saved_artifacts: list = []

        mock_db = MagicMock()
        mock_db.get.return_value = None          # document_id=None → get not called
        mock_db.save.side_effect = saved_artifacts.append

        from fichero.workflows.tools.llm_base import save_artifact

        with patch("fichero.db.db_manager") as mgr, \
             patch(
                 "fichero.workflows.tools.llm_base.find_document_by_path",
                 return_value=parent_pdf,
             ):
            mgr.get_database.return_value = mock_db
            await save_artifact(
                document_id=None,             # no explicit id → file_path lookup is OK
                file_path="/lib/book.pdf",
                content="Book transcription.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
            )

        assert saved_artifacts, "file_path fallback must still work when document_id=None"
        artifact = saved_artifacts[0]
        assert artifact.document_id == "parent-pdf-id", (
            f"file_path fallback must resolve to parent_pdf_id, got: {artifact.document_id}"
        )


class TestFindExistingArtifactPageChildResolution:
    """
    find_existing_artifact has the same file_path fallback as save_artifact.
    If it resolves to the parent PDF and finds old parent-level artifacts,
    skip_if_artifact_exists would silently reuse a wrong cached artifact.
    """

    def test_returns_none_when_document_id_given_but_not_found(self):
        """
        #2430: find_existing_artifact must not resolve via file_path when
        document_id was explicitly provided but db.get returns None.
        """
        parent_pdf = _make_document("parent-pdf-id", path="/lib/scan.pdf")
        fake_artifact = MagicMock()
        fake_artifact.content = "Stale parent artifact."
        fake_artifact.id = "stale-artifact-id"
        fake_artifact.created_at = 0

        mock_db = MagicMock()
        mock_db.get.return_value = None          # page child not found
        mock_db.query.return_value = [parent_pdf]  # file_path would find parent

        from fichero.workflows.tools.llm_base import find_existing_artifact

        with patch("fichero.db.db_manager") as mgr:
            mgr.get_database.return_value = mock_db
            result = find_existing_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                artifact_type="transcription",
                library_path="/lib",
            )

        # After fix: must return None (no document found) rather than
        # silently returning a parent-level artifact.
        assert result is None, (
            f"#2430: find_existing_artifact must return None when document_id "
            f"is given but not found — got: {result}"
        )
