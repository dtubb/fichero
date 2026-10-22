"""Every registered tool is called as tool(inputs=..., state=...): a helper that slipped between `@register_tool(...)` and its tool
took the tool's name (3914c00c4: `detect_regions` became `_find_regions_with_kraken`, so every Detect Regions run failed with
"unexpected keyword argument 'inputs'"; cand 15 gate)."""
from __future__ import annotations

import inspect

from fichero_server.workflows import registry


def test_every_registered_tool_takes_inputs_and_state():
    registry._ensure_tools_loaded()
    wrong = {name: fn.__name__ for name, fn in registry._TOOLS.items()
             if not {"inputs", "state"} <= set(inspect.signature(inspect.unwrap(fn)).parameters)}
    assert wrong == {}, f"a registered tool cannot take inputs/state (a helper under its decorator?): {wrong}"


def test_detect_regions_is_registered_as_itself():
    from fichero_server.workflows.tools import detect_regions

    assert inspect.unwrap(registry.get_tool("detect_regions")) is detect_regions.detect_regions
