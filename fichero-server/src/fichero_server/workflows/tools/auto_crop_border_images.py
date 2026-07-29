"""Append reversible auto-crop-border operations for selected scans."""
from __future__ import annotations
from typing import Any
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero_server.workflows.types import DataType, PortDef, State

@register_tool(name="auto_crop_border_images", display_name="Auto Crop Scan Borders", description="Detect and crop dark scan margins locally.", category="transform", icon="crop", color="orange", uses_llm=False, supports_batch=True, input_ports=[PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False)], output_ports=[], config_schema={}, sort_order=29)
async def auto_crop_border_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    operations = append_image_edit_operations(inputs, state, lambda _doc: {"op": "auto_crop_border", "page": int(inputs.get("page", 1)), "params": {}})
    return {"image_edit_operations": operations, "output_files": []}
