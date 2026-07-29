"""Sub-workflow composition tool."""

from __future__ import annotations

from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.subworkflow import sub_workflow as run_sub_workflow
from fichero_server.workflows.types import DataType, PortDef, State


SUB_WORKFLOW_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "workflow_ref": {
            "type": "string",
            "description": "Literal child workflow id or template name.",
        },
        "workflow_version": {"type": "string"},
        "input_contract": {"type": "array", "default": []},
        "output_contract": {"type": "array", "default": []},
        "output_mapping": {"type": "object", "default": {}},
        "max_depth": {"type": "integer", "minimum": 1, "maximum": 16, "default": 4},
        "allow_partial": {"type": "boolean", "default": False},
    },
    "required": ["workflow_ref"],
}


@register_tool(
    name="sub_workflow",
    display_name="Sub-Workflow",
    description="Run a child workflow behind declared input/output contracts.",
    category="workflow",
    icon="rectangle.stack",
    color="teal",
    input_ports=[
        PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
        )
    ],
    output_ports=[
        PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.ANY,
            required=False,
        )
    ],
    config_schema=SUB_WORKFLOW_CONFIG_SCHEMA,
    uses_llm=False,
    supports_batch=False,
    sort_order=95,
)
async def sub_workflow(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    return await run_sub_workflow(inputs, state, llm_config)
