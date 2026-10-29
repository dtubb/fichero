"""The plan says, in words, which kind of page a different model reads than the step's own (#6269): no silent switch."""
from __future__ import annotations

from fichero_server.api.routes.system.recipes import _reader_notes


def test_a_kind_read_by_another_model_is_named_and_a_same_model_kind_is_not():
    run = {"steps": ["read"], "model_override": "claude-sonnet-4-6",
           "readers": {"handwriting": {"model_override": "apple-vision", "note": "Apple Vision"},
                       "print": {"model_override": "claude-sonnet-4-6"}}}
    (note,) = _reader_notes([run])
    assert "handwriting pages are read by apple-vision, not claude-sonnet-4-6" in note and "Apple Vision" in note
    assert _reader_notes([{"model_override": "x"}]) == []
