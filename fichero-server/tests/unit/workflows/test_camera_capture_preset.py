"""Tests for the camera/DSLR watched-folder capture preset."""

from __future__ import annotations

from fichero_server.workflows.default_workflows import _load_preset_files


def test_rotate_auto_orient_images_ships_as_camera_capture_preset():
    presets = {p["name"]: p for p in _load_preset_files()}
    preset = presets["Rotate / Auto-Orient Images"]

    assert "camera/DSLR watched-folder capture preset" in preset["description"]
    assert "capture" in preset.get("tags", [])
    assert "camera" in preset.get("tags", [])
    assert "dslr" in preset.get("tags", [])
    assert "watch-folder" in preset.get("tags", [])
    assert preset.get("config", {}).get("preset_version") == 2

    node_tools = {n["tool"] for n in preset["nodes"]}
    assert node_tools == {"files", "rotate_images"}
