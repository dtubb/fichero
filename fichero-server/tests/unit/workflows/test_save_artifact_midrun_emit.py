"""Mid-run change-stream emission from the artifact save path (#4318).

When a workflow tool promotes its output into ``Document.page_content``
(``update_page_content=True``), the save must broadcast ``document.updated``
IMMEDIATELY — not only at the run boundary (``completion.finalize_run_documents``)
— so an open window shows fresh transcription text without reselecting the page,
and a CLI-launched run updates an open window identically.

The emit must NOT fire when nothing document-side was written (artifact-only
tools) or when a user edit blocked the promotion.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fichero_server.workflows.tools.llm_base import LLMToolConfig, save_artifact


@pytest.fixture
def llm_config() -> MagicMock:
    cfg = MagicMock()
    cfg.provider = "mock"
    cfg.model = "mock-1"
    return cfg


def _make_doc(metadata: dict | None = None, parent_id: str | None = "parent-1") -> MagicMock:
    doc = MagicMock()
    doc.id = "doc-1"
    doc.name = "page.jpg"
    doc.parent_id = parent_id
    doc.metadata = metadata if metadata is not None else {}
    doc.page_content = "original content"
    return doc


def _tool_config(update_page_content: bool) -> LLMToolConfig:
    return LLMToolConfig(
        artifact_type="transcription",
        update_page_content=update_page_content,
        trigger_embedding=False,
    )


async def _run_save(doc, tool_config, llm_config, emit_mock, task_id="thread-42"):
    db = MagicMock()
    db.get.return_value = doc
    db.path = "/tmp/lib.fichero/library.duckdb"
    db.query.return_value = []
    with (
        patch("fichero_server.db.db_manager.get_database", return_value=db),
        patch(
            "fichero_server.workflows.tools._workflow_change_emit.emit_change",
            emit_mock,
        ),
    ):
        return await save_artifact(
            document_id="doc-1",
            file_path=None,
            content="OCR result",
            data=None,
            library_path="/tmp/lib.fichero",
            llm_config=llm_config,
            task_id=task_id,
            tool_config=tool_config,
        )


class TestMidRunDocumentEmit:
    @pytest.mark.asyncio
    async def test_page_content_promotion_emits_document_updated(self, llm_config):
        """The mid-run page_content write broadcasts document.updated with the
        page id, its parent, and the run's thread id."""
        emit = MagicMock()
        doc = _make_doc()

        artifact_id = await _run_save(doc, _tool_config(True), llm_config, emit)

        assert artifact_id is not None
        assert doc.page_content == "OCR result"
        doc_updates = [
            c for c in emit.call_args_list
            if c.kwargs.get("type") == "document.updated"
        ]
        assert len(doc_updates) == 1
        call = doc_updates[0]
        assert call.kwargs["document_ids"] == ["doc-1"]
        assert call.kwargs["run_id"] == "thread-42"
        assert call.kwargs["actor"] == "workflow"
        assert call.kwargs["document_parents"] == {"doc-1": "parent-1"}

    @pytest.mark.asyncio
    async def test_rootless_page_omits_parent_map_but_still_emits(self, llm_config):
        """An unknown parent is OMITTED from document_parents (never guessed) —
        the event still fires so the window refreshes."""
        emit = MagicMock()
        doc = _make_doc(parent_id=None)

        await _run_save(doc, _tool_config(True), llm_config, emit)

        doc_updates = [
            c for c in emit.call_args_list
            if c.kwargs.get("type") == "document.updated"
        ]
        assert len(doc_updates) == 1
        assert not doc_updates[0].kwargs.get("document_parents")

    @pytest.mark.asyncio
    async def test_no_emit_when_tool_does_not_promote_page_content(self, llm_config):
        """Artifact-only tools write no document row mid-run — no document.updated."""
        emit = MagicMock()
        doc = _make_doc()

        artifact_id = await _run_save(doc, _tool_config(False), llm_config, emit)

        assert artifact_id is not None
        assert not [
            c for c in emit.call_args_list
            if c.kwargs.get("type") == "document.updated"
        ]

    @pytest.mark.asyncio
    async def test_no_emit_when_user_edit_blocks_promotion(self, llm_config):
        """A user-edited page keeps its text; no document.updated is broadcast
        for a write that did not happen."""
        emit = MagicMock()
        doc = _make_doc(
            metadata={"page_content_user_edited_at": "2026-04-22T12:00:00"}
        )

        artifact_id = await _run_save(doc, _tool_config(True), llm_config, emit)

        assert artifact_id is not None
        assert doc.page_content == "original content"
        assert not [
            c for c in emit.call_args_list
            if c.kwargs.get("type") == "document.updated"
        ]
