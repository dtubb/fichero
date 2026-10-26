"""A prompted vision tool on Apple Vision is refused once, before the run (#6029, `source.model.prompted-tool-on-apple-vision-refused-once`):
Apple Vision ignores the prompt, so the read-time refusal fired once per page (220 times in one run)."""
from __future__ import annotations

import importlib
import pkgutil

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows import tools as tools_package
from fichero_server.workflows.registry import TOOL_DEFS, TOOLS
from fichero_server.workflows.tools.vision_base import VisionToolConfig
from fichero_server.workflows.types import NodeDef
from fichero_server.workflows.validation import validate_workflow_llm_preflight
from tests.unit.workflows.test_preflight_credentials import _common_env, _workflow_for


def _tools_that_cannot_run_on_apple_vision() -> dict[str, str]:
    """tool name -> module, for every registered tool whose module's config says it does not support Apple Vision."""
    for info in pkgutil.iter_modules(tools_package.__path__):
        importlib.import_module(f"{tools_package.__name__}.{info.name}")
    found = {}
    for name, function in TOOLS.items():
        config = getattr(importlib.import_module(function.__module__), "TOOL_CONFIG", None)
        if isinstance(config, VisionToolConfig) and not config.supports_apple_vision:
            found[name] = function.__module__
    return found


def test_there_are_tools_that_cannot_run_on_apple_vision():
    assert {"describe", "tags", "classify"} <= set(_tools_that_cannot_run_on_apple_vision())


def test_every_tool_that_cannot_run_on_apple_vision_says_it_needs_a_generative_model():
    missing = sorted(name for name in _tools_that_cannot_run_on_apple_vision() if not TOOL_DEFS[name].requires_generative_model)
    assert not missing, f"{missing} would be refused page by page at read time, not once at preflight"


@pytest.mark.parametrize("tool", ["describe", "tags", "classify"])
def test_the_preflight_refuses_a_prompted_tool_on_apple_vision_once(monkeypatch, tool):
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(id="n", tool=tool, provider_name="apple", model_name="apple-vision")
    errors = validate_workflow_llm_preflight(_workflow_for(node), LLMConfig(provider="", model=""))
    assert len(errors) == 1 and "generation-capable vision model" in errors[0]
