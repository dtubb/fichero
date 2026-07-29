"""Append reversible local denoise operations to selected image chains (#3606)."""
from __future__ import annotations
from typing import Any
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero_server.workflows.types import DataType, PortDef, State

@register_tool(name="denoise_images", display_name="Denoise Images", description="Locally denoise selected scans without modifying sources.", category="transform", icon="sparkles", color="orange", uses_llm=False, supports_batch=True, input_ports=[PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False)], output_ports=[], config_schema={"radius": {"type": "integer", "default": 3, "minimum": 3, "maximum": 5}}, sort_order=27)
async def denoise_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    radius = 5 if int(inputs.get("radius", 3)) >= 5 else 3
    operations = append_image_edit_operations(inputs, state, lambda _doc: {"op": "denoise", "page": int(inputs.get("page", 1)), "params": {"radius": radius}})
    return {"image_edit_operations": operations, "output_files": []}
