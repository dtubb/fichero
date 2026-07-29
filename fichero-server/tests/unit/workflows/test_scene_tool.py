"""Coverage for scene classification prompt construction."""

from fichero_server.workflows.tools import scene as tool


def test_scene_prompt_switches_between_detail_and_choice_modes():
    detailed = tool.build_scene_prompt({"scenes": ["indoor"], "include_details": True})
    concise = tool.build_scene_prompt({"scenes": ["indoor"], "include_details": False})
    assert '"lighting"' in detailed and "Return ONLY valid JSON" in detailed
    assert "Return ONLY the scene type" in concise
