"""A page the in-flight budget cut is not a failed page: `process_vision` pauses the run (#6671).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.limits.rate-limit-backs-off-then-pauses`. A fake provider
keeps answering 402 `in_flight_budget_exhausted`; the retries are spent, the run is asked to pause, and the reader raises
`WorkflowPaused` instead of returning a page result with an `error`.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.execution.cancellation import WorkflowPaused, clear_pause, pause_requested
from fichero_server.llm import LLMConfig
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.node_context import set_current_node
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision
from tests.unit.workflows.test_in_flight_budget_6671 import _InFlight, _fresh  # noqa: F401 -- the autouse fixture


@pytest.mark.asyncio
async def test_a_page_cut_by_the_in_flight_budget_pauses_the_run_and_has_no_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cb, "compute_backoff_delay", lambda *a, **k: 0.0)
    monkeypatch.setenv("FICHERO_VISION_MAX_RETRIES", "2")
    set_current_node("read", run_id="run-6671")
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG stub")
    vision = AsyncMock(side_effect=_InFlight())
    try:
        with (
            patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
            patch("fichero_server.workflows.tools.vision_base.file_to_data_uri", return_value="data:image/png;base64,AAAA"),
            patch("fichero_server.llm.vision", new=vision),
            pytest.raises(WorkflowPaused),
        ):
            await process_vision(
                files=[str(image)], documents=[], prompt="Describe.",
                llm_config=LLMConfig(provider="openrouter", model="m", api_key="k"), library_path="", task_id=None,
                tool_config=VisionToolConfig(artifact_type="transcription", update_page_content=False,
                                             trigger_embedding=False, supports_apple_vision=True),
                vision_mode="llm")
        assert pause_requested("run-6671"), "the run is asked to pause with the cause"
        assert vision.await_count >= 2, "the call was retried before the run paused"
    finally:
        clear_pause("run-6671")
