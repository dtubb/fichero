"""Coverage for the denoise-images workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import denoise_images as tool


def test_denoise_clamps_radius_and_forwards_page(monkeypatch):
    monkeypatch.setattr(
        tool,
        "append_image_edit_operations",
        lambda inputs, state, operation: [operation("doc-1")],
    )

    result = asyncio.run(tool.denoise_images({"radius": 9, "page": "2"}, {}, object()))

    assert result["image_edit_operations"] == [
        {"op": "denoise", "page": 2, "params": {"radius": 5}}
    ]
    assert result["output_files"] == []


def test_denoise_defaults_to_minimum_radius(monkeypatch):
    monkeypatch.setattr(
        tool,
        "append_image_edit_operations",
        lambda inputs, state, operation: [operation("doc-1")],
    )

    result = asyncio.run(tool.denoise_images({"radius": 1}, {}, object()))

    assert result["image_edit_operations"][0]["params"]["radius"] == 3
