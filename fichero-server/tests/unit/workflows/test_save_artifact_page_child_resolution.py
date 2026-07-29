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
    `from fichero_server.db import db_manager`
so the correct patch target is "fichero_server.db.db_manager", not the llm_base module.
"""
from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

def _make_document(doc_id: str, path: str | None = None, page_content: str | None = None):
    from fichero_server.models import Document, DocType, Status
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
    from fichero_server.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


def _make_tool_config(*, update_page_content=True):
    from fichero_server.workflows.tools.vision_base import VisionToolConfig
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

        from fichero_server.workflows.tools.llm_base import save_artifact

        # db_manager is imported inside save_artifact; patch at the source module.
        with patch("fichero_server.db.db_manager") as mgr:
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
    async def test_no_orphan_when_db_get_misses_and_no_document(self, tmp_path):
        """
        #2430: the race is eliminated by passing the page-child document THROUGH
        (document=) so save_artifact never re-fetches by id across threads — see
        test_vision_wrapper_forwards_document_kwarg and the per-page placement
        tests for the saved-on-its-page proof.

        This test pins the COMPLEMENT: if NO document is passed AND db.get
        misses, the doc genuinely cannot be resolved. save_artifact must FAIL
        LOUD — return None, save NO artifact, and NEVER route to the parent PDF
        via the file_path fallback. No silent orphan, no silent reroute
        (the no-silent-fallback rule).
        """
        parent_pdf = _make_document("parent-pdf-id", path="/lib/scan.pdf")

        saved_artifacts: list = []

        mock_db = MagicMock()
        # db.get returns None — simulates the transient cross-connection miss.
        mock_db.get.return_value = None
        mock_db.save.side_effect = saved_artifacts.append

        from fichero_server.workflows.tools.llm_base import save_artifact

        with patch("fichero_server.db.db_manager") as mgr, \
             patch(
                 "fichero_server.workflows.tools.llm_base.find_document_by_path",
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
                # NB: no document= passed — the genuine-miss path.
            )

        # Genuine miss with no document passed → fail loud, never orphan/reroute.
        assert result is None, (
            "#2430: with no document passed and db.get missing, save_artifact "
            "must return None (a visible miss), not fabricate an orphan artifact."
        )
        saved_ids = [a.document_id for a in saved_artifacts if hasattr(a, "document_id")]
        # No orphan keyed on the unverified page id ...
        assert "page-child-id" not in saved_ids, (
            f"No orphan artifact may be saved on an unverified id. Got: {saved_ids}"
        )
        # ... and NEVER on the parent PDF.
        assert "parent-pdf-id" not in saved_ids, (
            f"#2430: save_artifact must NEVER route to the parent PDF. "
            f"Got: {saved_ids}"
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

        from fichero_server.workflows.tools.llm_base import save_artifact

        with patch("fichero_server.db.db_manager") as mgr, \
             patch(
                 "fichero_server.workflows.tools.llm_base.find_document_by_path",
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


class TestSaveArtifactDocumentValidation:
    """
    #2513: the document= pass-through (#2430) is validated UP FRONT, outside the
    catch-all try that absorbs DB-write failures. A malformed/partial dict must
    raise its ValidationError LOUD — never be swallowed and reported as a silent
    None artifact miss (the no-silent-fallback rule).
    """

    @pytest.mark.asyncio
    async def test_partial_dict_document_raises_loud(self, tmp_path):
        """A partial dict (missing required `name`) must raise, not return None."""
        from pydantic import ValidationError
        from fichero_server.workflows.tools.llm_base import save_artifact

        # Missing required Document fields (e.g. name/doc_type) → ValidationError.
        partial = {"id": "page-child-id"}

        # No db needed: validation fires before the try block touches db_manager.
        with pytest.raises(ValidationError):
            await save_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                content="Page 1.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                document=partial,           # malformed pass-through → must fail LOUD
            )

    @pytest.mark.asyncio
    async def test_full_dict_document_still_works(self, tmp_path):
        """A complete dict round-trips through model_validate and saves normally."""
        full_doc = _make_document("page-child-id", path=None).model_dump()

        saved_artifacts: list = []
        mock_db = MagicMock()
        mock_db.save.side_effect = saved_artifacts.append

        from fichero_server.workflows.tools.llm_base import save_artifact

        with patch("fichero_server.db.db_manager") as mgr:
            mgr.get_database.return_value = mock_db
            await save_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                content="Page 1.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                document=full_doc,          # full model_dump() → validates + saves
            )

        # db.get must NOT be used — the passed document is the resolution source.
        mock_db.get.assert_not_called()
        assert saved_artifacts, "full-dict document must still save the artifact"
        assert saved_artifacts[0].document_id == "page-child-id"

    @pytest.mark.asyncio
    async def test_none_document_uses_db_get_path(self, tmp_path):
        """document=None (the default) falls through to db.get by id — unchanged."""
        page_child = _make_document("page-child-id", path=None)

        saved_artifacts: list = []
        mock_db = MagicMock()
        mock_db.get.return_value = page_child
        mock_db.save.side_effect = saved_artifacts.append

        from fichero_server.workflows.tools.llm_base import save_artifact

        with patch("fichero_server.db.db_manager") as mgr:
            mgr.get_database.return_value = mock_db
            await save_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                content="Page 1.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                # document defaults to None → db.get path
            )

        mock_db.get.assert_called_once()
        assert saved_artifacts, "None document must resolve via db.get and save"
        assert saved_artifacts[0].document_id == "page-child-id"


class TestFindExistingArtifactPageChildResolution:
    """
    find_existing_artifact has the same file_path fallback as save_artifact.
    If it resolves to the parent PDF and finds old parent-level artifacts,
    skip_if_artifact_exists would silently reuse a wrong cached artifact.
    """

    def test_dedups_on_page_child_id_never_parent(self):
        """
        #2430: find_existing_artifact dedups against the EXPLICIT document_id,
        never the parent PDF. With the root-cause fix it queries artifacts
        directly by document_id (no racy db.get(Document) that could miss the
        page child and reroute to the parent), so a stale parent-level artifact
        can never mask a fresh per-page run.
        """
        # Stand-in for a stale artifact that lives on the PARENT PDF only.
        stale_parent_artifact = MagicMock()
        stale_parent_artifact.content = "Stale parent artifact."
        stale_parent_artifact.id = "stale-artifact-id"
        stale_parent_artifact.document_id = "parent-pdf-id"
        stale_parent_artifact.created_at = 0
        stale_parent_artifact.provider = None
        stale_parent_artifact.model = None

        def _query(model, **filters):
            # Only the parent has an artifact; the page child has none yet.
            if filters.get("document_id") == "parent-pdf-id":
                return [stale_parent_artifact]
            return []

        mock_db = MagicMock()
        mock_db.get.return_value = None          # would-be racy miss; must be unused
        mock_db.query.side_effect = _query

        from fichero_server.workflows.tools.llm_base import find_existing_artifact

        with patch("fichero_server.db.db_manager") as mgr:
            mgr.get_database.return_value = mock_db
            result = find_existing_artifact(
                document_id="page-child-id",
                file_path="/lib/scan.pdf",
                artifact_type="transcription",
                library_path="/lib",
            )

        # No artifact exists for the page child yet → None, and crucially the
        # parent's stale artifact is never returned.
        assert result is None, (
            f"#2430: find_existing_artifact must dedup on the page-child id and "
            f"must NOT return the parent's stale artifact — got: {result}"
        )
