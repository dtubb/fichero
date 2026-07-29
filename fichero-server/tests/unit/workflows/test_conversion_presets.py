"""Conversion preset wiring (#2265).

The representation picker (#2264) is fed by these shipped presets. Each must
load from the packaged resources, reference real registered tools, and use the
UI edge schema so they render in the workflow editor.
"""

from __future__ import annotations

import fichero_server.workflows.tools  # noqa: F401  (registers all tools)
from fichero_server.workflows.default_workflows import _load_preset_files
from fichero_server.workflows.registry import get_tool_def

PRESET_TARGET = {
    "Convert to Markdown": ("convert", {"target_format": "markdown"}),
    "Convert to HTML": ("convert", {"target_format": "html"}),
    "Convert to SVG": ("convert", {"target_format": "svg"}),
    "Extract Table": ("table_extract", {"output_style": "json_rows"}),
    "Extract Geo": ("extract_geo", {"online_geocoding": False}),
}


def _by_name() -> dict[str, dict]:
    return {p["name"]: p for p in _load_preset_files()}


def test_all_conversion_presets_present():
    names = set(_by_name())
    for expected in PRESET_TARGET:
        assert expected in names, f"missing preset: {expected}"


def test_presets_reference_registered_tools_with_expected_config():
    presets = _by_name()
    for name, (tool, config) in PRESET_TARGET.items():
        preset = presets[name]
        assert preset["format"] == "nodes"
        node_tools = {n["tool"] for n in preset["nodes"]}
        assert "files" in node_tools, f"{name} must start from a files source"
        assert tool in node_tools, f"{name} must use the {tool} tool"
        # Every referenced tool is actually registered.
        for node in preset["nodes"]:
            assert get_tool_def(node["tool"]) is not None, (
                f"{name} references unregistered tool {node['tool']!r}"
            )
        # The target node carries the expected representation config.
        target = next(n for n in preset["nodes"] if n["tool"] == tool)
        for key, value in config.items():
            assert target["config"].get(key) == value, (
                f"{name}: {tool}.{key} should be {value!r}"
            )


def test_preset_edges_use_ui_schema_and_connect_real_nodes():
    presets = _by_name()
    for name in PRESET_TARGET:
        preset = presets[name]
        node_ids = {n["id"] for n in preset["nodes"]}
        assert preset["edges"], f"{name} has no edges"
        for edge in preset["edges"]:
            for key in ("source", "target", "source_port", "target_port"):
                assert key in edge, f"{name} edge missing {key!r}: {edge}"
            assert edge["source"] in node_ids and edge["target"] in node_ids


def test_extract_geo_transcribes_before_geocoding():
    """extract_geo needs text, so the geo preset must run transcribe first."""
    geo = _by_name()["Extract Geo"]
    transcribe_id = next(n["id"] for n in geo["nodes"] if n["tool"] == "transcribe")
    geo_id = next(n["id"] for n in geo["nodes"] if n["tool"] == "extract_geo")
    assert any(
        e["source"] == transcribe_id
        and e["target"] == geo_id
        and e["target_port"] == "text"
        for e in geo["edges"]
    ), "transcribe.text must flow into extract_geo.text"
