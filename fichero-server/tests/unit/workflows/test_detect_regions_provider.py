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


@pytest.mark.asyncio
async def test_vlm_with_no_run_provider_resolves_the_settings_vision_tier():
    # The tool registers uses_llm=False, so a preset run arrives with an
    # EMPTY llm_config — the VLM branch must resolve the Settings vision
    # tier itself instead of dying with "provider not configured"
    # (Caciques Hoja 531, 2026-08-27).
    with (
        patch(
            "fichero_server.workflows.tools.detect_regions.process_vision",
            new=AsyncMock(return_value={"results": []}),
        ) as pv,
        patch(
            "fichero_server.llm.resolve_model_alias_for_capability",
            return_value=("openrouter", "google/gemini-3.1-flash-lite"),
        ) as resolve,
    ):
        await detect_regions(
            {"files": ["a.jpg"], "provider": "vlm"},
            _state(),
            LLMConfig(provider="", model=""),
        )
    resolve.assert_called_once_with(
        "$vision_medium", "", required_capability="vision"
    )
    cfg = pv.call_args.kwargs["llm_config"]
    assert cfg.provider == "openrouter"
    assert cfg.model == "google/gemini-3.1-flash-lite"


def test_vlm_node_counts_as_llm_for_override_and_vision():
    # The static ToolDef flag says no LLM; the node's own config says vision
    # LLM. The run menu's model picker, the runner's override filter, and
    # requires_vision all read this predicate (Daniel, 2026-08-27: "workflow
    # detect regions vlm should allow us to select which one, no?").
    from fichero_server.workflows.validation import (
        node_uses_llm,
        workflow_accepts_model_override,
        workflow_requires_vision,
    )

    apple = {"tool": "detect_regions", "config": {"provider": "apple"}}
    vlm = {"tool": "detect_regions", "config": {"provider": "vlm"}}
    assert not node_uses_llm(apple)
    assert node_uses_llm(vlm)
    assert not workflow_accepts_model_override([apple])
    assert workflow_accepts_model_override([vlm])
    assert not workflow_requires_vision([apple])
    assert workflow_requires_vision([vlm])
