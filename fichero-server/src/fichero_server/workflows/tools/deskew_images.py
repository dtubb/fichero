"""Append reversible auto-deskew operations for selected image documents."""
from __future__ import annotations
from typing import Any
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero_server.workflows.types import DataType, PortDef, State

@register_tool(name="deskew_images", display_name="Auto Deskew Images", description="Detect and straighten skewed scans locally.", category="transform", icon="rotate.right", color="orange", uses_llm=False, supports_batch=True, input_ports=[PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False)], output_ports=[], config_schema={}, sort_order=28)
async def deskew_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    library = state.get("library_path") or inputs.get("library_path")

    def straighten(doc):
        """The row carries the angle that was found (not "auto"); a page under 0.3 degrees gets no row."""
        from PIL import Image

        from fichero_server.media.image_ops import auto_straighten_angle
        from fichero_server.media.upright import upright
        from fichero_server.workflows.tools.sources import _resolve_abs_path

        try:
            with Image.open(_resolve_abs_path(doc, str(library))) as opened:
                angle = auto_straighten_angle(upright(opened))
        except (OSError, AttributeError, TypeError):
            return None
        return {"op": "auto_deskew", "page": int(inputs.get("page", 1)), "params": {"angle": angle}, "method": "hough"} if angle else None

    operations = append_image_edit_operations(inputs, state, straighten)
    return {"image_edit_operations": operations, "output_files": []}
