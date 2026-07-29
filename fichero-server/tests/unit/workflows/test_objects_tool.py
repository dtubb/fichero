"""Coverage for object-detection prompt construction."""

from fichero_server.workflows.tools import objects as tool


def test_objects_prompt_respects_detail_and_position_options():
    count = tool.build_objects_prompt({"detail_level": "count", "include_positions": True})
    basic = tool.build_objects_prompt({"detail_level": "basic", "include_positions": False})
    assert "total_objects" in count and '"categories"' in count
    assert "position" not in basic
    assert '"objects"' in basic
