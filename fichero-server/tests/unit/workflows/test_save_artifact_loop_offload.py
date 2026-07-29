"""
#2540: `save_artifact` must not pin the event loop.

The async per-file save path used to call the SYNCHRONOUS `db.save` / `db.embed`
(ONNX inference) directly on the event-loop thread, so every file blocked the
loop and nothing overlapped — which is why adding per-file concurrency did
nothing. The fix offloads the whole synchronous DB-write + embed sequence off
the loop via a single `asyncio.to_thread` hop (`_save_artifact_sync`).

This is the regression guard: we make the synchronous DB work SLOW (a blocking
`time.sleep` inside `db.save`), kick off `save_artifact` as a task, and prove
that OTHER async work on the SAME loop makes progress concurrently while the
slow save is in flight. If the sync work were still running on the loop, the
ticker coroutine could not advance until the save finished (ticks ~= 0).

NOTE: db_manager is imported INSIDE save_artifact via `from fichero_server.db import
db_manager`, so the patch target is "fichero_server.db.db_manager".
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


def _make_document(doc_id: str, path: str | None = None):
    from fichero_server.models import Document, DocType, Status
    return Document(
        id=doc_id,
        name="doc",
        doc_type=DocType.file,
        path=path,
        page_content=None,
        status=Status.pending,
        metadata={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _make_llm_config():
    from fichero_server.llm import LLMConfig
    return LLMConfig(provider="openai", model="gpt-4o")


def _make_tool_config():
    from fichero_server.workflows.tools.llm_base import LLMToolConfig
    return LLMToolConfig(
        artifact_type="transcription",
        update_page_content=False,
        trigger_embedding=False,
        skip_if_artifact_exists=False,
    )


@pytest.mark.asyncio
async def test_save_artifact_does_not_pin_event_loop():
    """A slow SYNCHRONOUS db.save must not block the loop — concurrent async
    work has to keep advancing while the save is in flight (#2540)."""
    from fichero_server.workflows.tools.llm_base import save_artifact

    SAVE_BLOCK_S = 0.30
    page_child = _make_document("page-child-id", path=None)

    mock_db = MagicMock()

    def _slow_blocking_save(_obj):
        # Stand-in for the real synchronous DB write + ONNX embed: a blocking,
        # non-async sleep. If this runs ON the event loop, the ticker below
        # cannot advance for SAVE_BLOCK_S; if it runs off-loop (to_thread), the
        # ticker interleaves freely.
        time.sleep(SAVE_BLOCK_S)

    mock_db.save.side_effect = _slow_blocking_save

    ticks = 0

    async def _ticker(stop: asyncio.Event):
        nonlocal ticks
        while not stop.is_set():
            await asyncio.sleep(0.01)
            ticks += 1

    with patch("fichero_server.db.db_manager") as mgr:
        mgr.get_database.return_value = mock_db

        stop = asyncio.Event()
        ticker_task = asyncio.create_task(_ticker(stop))
        # Yield once so the ticker is actually scheduled before the save starts.
        await asyncio.sleep(0)

        save_task = asyncio.create_task(
            save_artifact(
                document_id="page-child-id",
                file_path=None,
                content="page-1 transcription.",
                data=None,
                library_path="/lib",
                llm_config=_make_llm_config(),
                task_id=None,
                tool_config=_make_tool_config(),
                document=page_child,
            )
        )

        artifact_id = await save_task
        stop.set()
        await ticker_task

    # The save genuinely happened on the page child (behaviour preserved).
    assert artifact_id is not None
    assert mock_db.save.called

    # The loop was NOT pinned: with a ~0.30s blocking save and 0.01s ticks, an
    # unblocked loop yields ~25+ ticks. If the sync save had run on the loop the
    # ticker would have been frozen for the whole window (~0 ticks). A generous
    # floor keeps this robust on a loaded CI box while still failing hard on a
    # regression that puts the blocking work back on the loop.
    assert ticks >= 10, (
        f"event loop appears pinned during save_artifact: only {ticks} ticks "
        f"elapsed during a {SAVE_BLOCK_S}s blocking save (expected many). The "
        f"synchronous DB/embed work must run off-loop via asyncio.to_thread."
    )
