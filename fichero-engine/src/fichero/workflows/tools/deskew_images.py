"""Append reversible auto-deskew operations for selected image documents."""
from __future__ import annotations
from typing import Any
from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero.workflows.types import DataType, PortDef, State

@register_tool(name="deskew_images", display_name="Auto Deskew Images", description="Detect and straighten skewed scans locally.", category="transform", icon="rotate.right", color="orange", uses_llm=False, supports_batch=True, input_ports=[PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False)], output_ports=[], config_schema={}, sort_order=28)
async def deskew_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    operations = append_image_edit_operations(inputs, state, lambda _doc: {"op": "auto_deskew", "page": int(inputs.get("page", 1)), "params": {}})
    return {"image_edit_operations": operations, "output_files": []}
