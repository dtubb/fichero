"""Coverage for the deskew-images workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import deskew_images as tool


def test_deskew_appends_auto_deskew_operation(monkeypatch):
    monkeypatch.setattr(
        tool,
        "append_image_edit_operations",
        lambda inputs, state, operation: [operation("doc-1")],
    )

    result = asyncio.run(tool.deskew_images({"page": "4"}, {}, object()))

    assert result == {
        "image_edit_operations": [{"op": "auto_deskew", "page": 4, "params": {}}],
        "output_files": [],
    }
