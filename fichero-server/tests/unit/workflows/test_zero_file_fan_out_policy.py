"""Zero-file runs FAIL loudly (Daniel, 2026-08-11).

A fan-out that receives 0 files used to return [] (or route to a Send-less
_process hop) and the run completed GREEN — absence read as success. Now it
raises, with ONE deliberate exception: a search source finding nothing is a
result, not a failure (sources.py returns empty by design for it).
"""

import pytest

from fichero_server.workflows.builder import (
    _make_fan_out_function,
    _make_route_map_fan_out_function,
)

NODE_NAMES = {"src": "files_1", "tgt": "transcribe_1"}


def _state_with_files(files):
    return {"outputs": {"src": {"files": files, "documents": []}}}


class TestDirectFanOut:
    def _fan_out(self, source_tool):
        return _make_fan_out_function(
            "src", ["tgt"], NODE_NAMES, source_tool=source_tool
        )

    @pytest.mark.parametrize("source_tool", ["files", "folder", "collection", None])
    def test_zero_files_raises(self, source_tool):
        with pytest.raises(ValueError, match="0 files"):
            self._fan_out(source_tool)(_state_with_files([]))

    def test_zero_files_from_search_completes_empty(self):
        assert self._fan_out("search")(_state_with_files([])) == []

    def test_nonzero_files_still_fan_out(self):
        sends = self._fan_out("folder")(_state_with_files(["/a.jpg", "/b.jpg"]))
        assert len(sends) == 2


class TestRouteMapFanOut:
    def _route_fn(self, source_tool):
        return _make_route_map_fan_out_function(
            route_key="$.nodes.classify.value",
            route_map={"typescript": "tgt"},
            node_names=NODE_NAMES,
            route_map_parallel={"tgt": "src"},
            source_tool_by_id={"src": source_tool} if source_tool else {},
        )

    def _routed_state(self, files):
        state = _state_with_files(files)
        state["outputs"]["classify"] = {"value": "typescript"}
        return state

    def test_zero_files_raises(self):
        with pytest.raises(ValueError, match="0 files"):
            self._route_fn("folder")(self._routed_state([]))

    def test_zero_files_from_search_routes_to_process(self):
        result = self._route_fn("search")(self._routed_state([]))
        assert result == "transcribe_1_process"

    def test_nonzero_files_still_fan_out(self):
        sends = self._route_fn("folder")(self._routed_state(["/a.jpg"]))
        assert isinstance(sends, list) and len(sends) == 1
