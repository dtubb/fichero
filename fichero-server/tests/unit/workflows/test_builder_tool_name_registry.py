"""Fan-out tool names must resolve, and the vision cap must be tunable.

PARALLEL_TOOLS / SOURCE_TOOLS are matched against NodeDef.tool by string
membership (builder.build_graph's parallel-edge detection). A name in either
set that no registered tool answers to silently disables per-file fan-out —
"entities" sat in PARALLEL_TOOLS while the tool was registered as
"extract_entities", so a source→extract_entities edge ran as a single batch
call. These tests make that class of drift loud.

FICHERO_VISION_FAN_OUT_CONCURRENCY is the throughput ceiling for every
multi-page vision run; the resolver must honour a valid override and fall
back loudly (never unbounded) on garbage.
"""

import pytest

from fichero_server.workflows import builder
from fichero_server.workflows.builder import (
    _DEFAULT_VISION_FAN_OUT_CONCURRENCY,
    _vision_fan_out_concurrency,
    PARALLEL_TOOLS,
    SOURCE_TOOLS,
)
from fichero_server.workflows.registry import get_tool


class TestFanOutToolNamesResolve:
    @pytest.mark.parametrize("name", sorted(PARALLEL_TOOLS))
    def test_parallel_and_source_tool_names_resolve(self, name):
        assert get_tool(name) is not None, (
            f"PARALLEL_TOOLS entry {name!r} does not resolve via get_tool — "
            "fan-out for it is silently disabled"
        )

    @pytest.mark.parametrize("name", sorted(SOURCE_TOOLS))
    def test_source_tool_names_resolve(self, name):
        assert get_tool(name) is not None, (
            f"SOURCE_TOOLS entry {name!r} does not resolve via get_tool — "
            "parallel-edge detection for it is silently disabled"
        )

    def test_extract_entities_is_a_parallel_tool(self):
        # The regression this file exists for: the registered name, not the
        # historical "entities" shorthand.
        assert "extract_entities" in PARALLEL_TOOLS
        assert "entities" not in PARALLEL_TOOLS


class TestVisionFanOutConcurrencyEnv:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("FICHERO_VISION_FAN_OUT_CONCURRENCY", raising=False)
        assert _vision_fan_out_concurrency() == _DEFAULT_VISION_FAN_OUT_CONCURRENCY

    def test_valid_override(self, monkeypatch):
        monkeypatch.setenv("FICHERO_VISION_FAN_OUT_CONCURRENCY", "12")
        assert _vision_fan_out_concurrency() == 12

    @pytest.mark.parametrize("raw", ["", "  ", "nope", "0", "-3"])
    def test_garbage_falls_back_to_default(self, raw, monkeypatch):
        monkeypatch.setenv("FICHERO_VISION_FAN_OUT_CONCURRENCY", raw)
        assert _vision_fan_out_concurrency() == _DEFAULT_VISION_FAN_OUT_CONCURRENCY

    def test_module_constant_is_positive(self):
        assert builder.VISION_FAN_OUT_CONCURRENCY >= 1
