"""
Tests for issue #672 — workflows must not overwrite user-edited page_content.

The protection is a timestamp: when the API update route writes page_content,
it sets metadata["page_content_user_edited_at"]. save_artifact checks that
metadata and skips the page_content overwrite when the flag is set.

These tests exercise save_artifact directly with mocked DB so we verify the
branching without hitting DuckDB.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from fichero_server.workflows.tools.llm_base import LLMToolConfig, save_artifact


@pytest.fixture
def llm_config() -> MagicMock:
    cfg = MagicMock()
    cfg.provider = "mock"
    cfg.model = "mock-1"
    return cfg


@pytest.fixture
def tool_config() -> LLMToolConfig:
    return LLMToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
    )


def _make_doc(metadata: dict | None = None) -> MagicMock:
    doc = MagicMock()
    doc.id = "doc-1"
    doc.name = "page.jpg"
    doc.metadata = metadata if metadata is not None else {}
    doc.page_content = "original content"
    return doc


class TestUserEditProtection:
    @pytest.mark.asyncio
    async def test_page_content_updated_when_no_user_edit_flag(
        self, llm_config, tool_config
    ):
        """Tool workflows update page_content on a pristine document."""
        doc = _make_doc(metadata={})
        db = MagicMock()
        db.get.return_value = doc
        db.save = MagicMock()
        db.embed = MagicMock()

        with patch("fichero_server.db.db_manager.get_database", return_value=db):
            artifact_id = await save_artifact(
                document_id="doc-1",
                file_path=None,
                content="OCR result",
                data=None,
                library_path="/tmp/lib.fichero",
                llm_config=llm_config,
                task_id="t",
                tool_config=tool_config,
            )

        assert artifact_id is not None
        assert doc.page_content == "OCR result"

    @pytest.mark.asyncio
    async def test_page_content_preserved_when_user_edit_flag_set(
        self, llm_config, tool_config
    ):
        """A user-edited document's page_content must not be overwritten."""
        doc = _make_doc(
            metadata={"page_content_user_edited_at": "2026-04-22T12:00:00"}
        )
        db = MagicMock()
        db.get.return_value = doc
        db.save = MagicMock()
        db.embed = MagicMock()

        with patch("fichero_server.db.db_manager.get_database", return_value=db):
            artifact_id = await save_artifact(
                document_id="doc-1",
                file_path=None,
                content="New OCR text that should NOT overwrite",
                data=None,
                library_path="/tmp/lib.fichero",
                llm_config=llm_config,
                task_id="t",
                tool_config=tool_config,
            )

        # Artifact was still saved — the user can see the new OCR result
        # on the Artifacts tab and manually promote it if they want.
        assert artifact_id is not None
        # page_content is preserved unchanged (no mutation happened via setattr).
        assert doc.page_content == "original content"

    @pytest.mark.asyncio
    async def test_metadata_with_none_does_not_trigger_protection(
        self, llm_config, tool_config
    ):
        """A document with metadata=None (not dict) falls through as pristine."""
        doc = _make_doc(metadata={})
        doc.metadata = None  # force the non-dict branch
        db = MagicMock()
        db.get.return_value = doc
        db.save = MagicMock()
        db.embed = MagicMock()

        with patch("fichero_server.db.db_manager.get_database", return_value=db):
            artifact_id = await save_artifact(
                document_id="doc-1",
                file_path=None,
                content="OCR result",
                data=None,
                library_path="/tmp/lib.fichero",
                llm_config=llm_config,
                task_id="t",
                tool_config=tool_config,
            )

        # metadata-not-dict path should be treated as "no protection": the
        # outer save_artifact coerces metadata to a dict, so the page_content
        # update succeeds normally.
        assert artifact_id is not None
