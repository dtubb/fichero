"""verify_workflows reads its image-input tools from the live registry (dev-workflows.run.loop-needs-maintainer):
adding an image node never edits the pinned script."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("verify_workflows", Path(__file__).resolve().parents[4] / "scripts" / "verify_workflows.py")
vw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vw)


def _tool(category, *types):
    return {"category": category, "input_ports": [{"data_type": t} for t in types]}


def test_a_new_image_tool_in_the_registry_is_in_the_list_with_no_edit_to_the_script():
    defs = {"brand_new_images": _tool("transform", "files", "json"), "new_reader": _tool("vision", "files", "any"),
            "summarize": _tool("llm", "text"), "audio_transcribe": _tool("audio", "files"), "files": _tool("source", "text")}
    assert vw.image_input_tools(defs) == {"brand_new_images", "new_reader", "sub_workflow"}


def test_the_shipped_registry_still_names_the_core_image_tools():
    from fichero_server.api.routes.workflow.workflows import _tool_to_response
    from fichero_server.workflows.registry import list_executable_tools

    defs = {t.name: _tool_to_response(t).model_dump(mode="json") for t in list_executable_tools()}
    assert {"transcribe", "rotate_images", "split_pages", "prepare_images", "similarity", "zoom"} <= vw.image_input_tools(defs)
    assert not {"summarize", "to_excel", "audio_transcribe", "files"} & vw.image_input_tools(defs)


def test_the_floor_keeps_the_image_tools_whose_port_is_json_so_the_registry_rule_drops_none():
    """Review 2026-11-02: the registry rule alone dropped denoise/deskew/autocrop/binarize (a JSON port) and organize_same_documents."""
    names = ("denoise_images", "deskew_images", "auto_crop_border_images", "adaptive_binarize_images", "organize_same_documents")
    defs = {n: {"category": "transform" if n.endswith("_images") else "utility", "input_ports": [{"data_type": "json"}]} for n in names}
    assert set(names) <= vw.image_input_tools(defs)
    assert vw.image_input_tools({}) == {"sub_workflow"}, "a floor name not in the registry is not invented"
    assert vw.IMAGE_INPUT_FLOOR >= set(names)
