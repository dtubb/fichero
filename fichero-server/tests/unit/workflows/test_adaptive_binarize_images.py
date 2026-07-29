"""Coverage for the adaptive-binarize workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import adaptive_binarize_images as tool


def test_adaptive_binarize_appends_operation_and_returns_empty_files(monkeypatch):
    captured = {}

    def fake_append(inputs, state, operation):
        captured.update(inputs=inputs, state=state)
        return [operation("doc-1")]

    monkeypatch.setattr(tool, "append_image_edit_operations", fake_append)
    inputs = {"documents": ["doc-1"], "page": "3"}
    state = {"library_path": "/tmp/lib"}

    result = asyncio.run(tool.adaptive_binarize_images(inputs, state, object()))

    assert captured == {"inputs": inputs, "state": state}
    assert result == {
        "image_edit_operations": [{"op": "adaptive_binarize", "page": 3, "params": {}}],
        "output_files": [],
    }


def test_adaptive_binarize_defaults_to_first_page(monkeypatch):
    monkeypatch.setattr(
        tool,
        "append_image_edit_operations",
        lambda inputs, state, operation: [operation("doc-1")],
    )

    result = asyncio.run(tool.adaptive_binarize_images({}, {}, object()))

    assert result["image_edit_operations"][0]["page"] == 1
