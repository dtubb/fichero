"""Detect Regions (VLM) must not run on a recognition-only model.

Daniel, 2026-09-01: "Detect Regions with a VLM on Apple Vision fails."

It did not fail loudly — that was the problem. The VLM branch only substituted
a vision model when the resolved provider was EMPTY, so an Apple-pinned run
sent the boxes prompt to Apple Vision, which ignores prompts and returns plain
OCR text; the geometry parser then found no JSON and produced a regions
artifact with no boxes at all.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import detect_regions as detect_regions_module


def _run(inputs, llm_config):
    return asyncio.run(
        detect_regions_module.detect_regions(inputs, {}, llm_config)
    )


def test_apple_pinned_vlm_run_is_refused_when_the_vision_tier_is_also_apple(
    monkeypatch,
):
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, required_capability=None: ("apple", "apple-vision"),
    )

    with pytest.raises(ValueError) as excinfo:
        _run(
            {"provider": "vlm", "files": []},
            LLMConfig(provider="apple", model="apple-vision"),
        )

    message = str(excinfo.value)
    assert "Apple Vision" in message
    # The refusal has to say what to DO — a preflight that only says "no" sends
    # the user back to the same broken pick.
    assert "Vision default" in message or "pin one" in message


def test_apple_pinned_vlm_run_substitutes_the_configured_vision_model(monkeypatch):
    """The normal recovery: Settings has a real VLM, so use it."""
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, required_capability=None: ("openai", "gpt-5"),
    )

    async def _fake_process_vision(*args, **kwargs):
        captured["llm_config"] = kwargs.get("llm_config") or (
            args[2] if len(args) > 2 else None
        )
        captured["kwargs"] = kwargs
        return {}

    monkeypatch.setattr(
        detect_regions_module, "process_vision", _fake_process_vision
    )

    _run(
        {"provider": "vlm", "files": []},
        LLMConfig(provider="apple", model="apple-vision"),
    )

    config = captured["kwargs"].get("llm_config")
    assert config is not None, "process_vision must be given the resolved config"
    assert config.provider == "openai"
    assert config.model == "gpt-5"


def test_substituted_default_that_cannot_serve_fails_loud_and_named(monkeypatch):
    """No model was picked for the run, so the step falls to the configured
    Vision default — an unpicked local MLX model that isn't installed. It must
    FAIL LOUD and NAMED, not die as an opaque 'All parallel branches failed …
    not installed' (Daniel 2026-09-07 no-silent-substitution)."""
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, required_capability=None: (
            "omlx",
            "mlx-community/Qwen3-VL-8B",
        ),
    )

    async def _fake_process_vision(*args, **kwargs):
        # process_vision swallows the provider/runtime error into per-file
        # result["error"] (it degrades rather than raising).
        return {
            "results": [
                {
                    "file": "p1.png",
                    "text": "",
                    "value": None,
                    "error": "Local model mlx-community/Qwen3-VL-8B is not installed.",
                }
            ]
        }

    monkeypatch.setattr(
        detect_regions_module, "process_vision", _fake_process_vision
    )

    with pytest.raises(ValueError) as excinfo:
        _run(
            {"provider": "vlm", "files": ["p1.png"]},
            # Empty config == the run's choice never reached this node.
            LLMConfig(provider="", model=""),
        )

    message = str(excinfo.value)
    assert "omlx/mlx-community/Qwen3-VL-8B" in message
    assert "configured Vision default" in message
    # The underlying reason is surfaced, not hidden.
    assert "not installed" in message


def test_a_run_pick_is_used_and_never_reframed_as_a_default(monkeypatch):
    """When the run's cloud choice DOES reach the node it is used verbatim, and
    a provider error on it is NOT reframed as a configured-default failure — the
    substitution branch is not entered at all."""
    captured: dict[str, object] = {}

    async def _fake_process_vision(*args, **kwargs):
        captured["llm_config"] = kwargs.get("llm_config")
        # Even if this pick errored, detect_regions must not raise the
        # configured-default message — that path is only for substitutions.
        return {"results": [{"file": "p1.png", "text": "boxes", "value": None}]}

    monkeypatch.setattr(
        detect_regions_module, "process_vision", _fake_process_vision
    )

    result = _run(
        {"provider": "vlm", "files": ["p1.png"]},
        LLMConfig(provider="google", model="gemini-3-pro-preview"),
    )
    config = captured["llm_config"]
    assert config.provider == "google"
    assert config.model == "gemini-3-pro-preview"
    assert "results" in result
