"""Detect Regions' provider option (Daniel, 2026-08-23: "some of these
documents are hard hard to read") — apple stays the free default; vlm routes
the page to the RUN's chosen vision model and asks it for boxes."""
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.detect_regions import detect_regions


def _state():
    return {"library_path": "/tmp/lib", "task_id": "t1", "input_files": []}


@pytest.mark.asyncio
async def test_apple_default_forces_the_local_provider():
    run_config = LLMConfig(provider="openrouter", model="qwen-vl")
    with patch(
        "fichero_server.workflows.tools.detect_regions.process_vision",
        new=AsyncMock(return_value={"results": []}),
    ) as pv:
        await detect_regions({"files": ["a.jpg"]}, _state(), run_config)
    kwargs = pv.call_args.kwargs
    assert kwargs["vision_mode"] == "apple"
    assert kwargs["llm_config"].provider == "apple"
    assert kwargs["prompt"] == ""
    assert not kwargs.get("return_boxes")


@pytest.mark.asyncio
async def test_vlm_provider_uses_the_runs_model_and_forces_boxes():
    run_config = LLMConfig(provider="openrouter", model="qwen-vl")
    with patch(
        "fichero_server.workflows.tools.detect_regions.process_vision",
        new=AsyncMock(return_value={"results": []}),
    ) as pv:
        await detect_regions(
            {"files": ["a.jpg"], "provider": "vlm"}, _state(), run_config
        )
    kwargs = pv.call_args.kwargs
    assert kwargs["vision_mode"] == "llm"
    # The RUN's model, not a forced local one — the whole point of the option.
    assert kwargs["llm_config"] is run_config
    assert kwargs["return_boxes"] is True
    # Any vision model may be asked; the orphan guard is the safety net, not
    # a provider allow-list.
    assert kwargs["force_return_boxes"] is True
    assert "box" in kwargs["prompt"].lower()
