"""Append reversible adaptive-binarize operations for selected scans."""
from __future__ import annotations
from typing import Any
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero_server.workflows.types import DataType, PortDef, State

@register_tool(name="adaptive_binarize_images", display_name="Adaptive Binarize Images", description="Locally clean uneven scan backgrounds into black and white.", category="transform", icon="circle.lefthalf.filled", color="orange", uses_llm=False, supports_batch=True, input_ports=[PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False)], output_ports=[], config_schema={}, sort_order=30)
async def adaptive_binarize_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    operations = append_image_edit_operations(inputs, state, lambda _doc: {"op": "adaptive_binarize", "page": int(inputs.get("page", 1)), "params": {}})
    return {"image_edit_operations": operations, "output_files": []}
