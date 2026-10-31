"""Coverage for the deskew-images workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import deskew_images as tool


def test_deskew_writes_no_row_for_a_page_it_cannot_read(monkeypatch):
    """The row now carries the angle found (`tests/unit/media/test_turn_straighten_blank.py`); with no image to measure there
    is no angle and so no row, where it used to write an \"auto\" row that measured nothing."""
    monkeypatch.setattr(
        tool,
        "append_image_edit_operations",
        lambda inputs, state, operation: [operation("doc-1")],
    )

    result = asyncio.run(tool.deskew_images({"page": "4"}, {}, object()))

    assert result == {
        "image_edit_operations": [None],
        "output_files": [],
    }
