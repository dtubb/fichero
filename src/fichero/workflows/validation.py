"""
Tool Validation Functions

Functions for validating tool connections, node configurations, and workflow structure.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero.workflows.types import (
    PortDef,
    NodeDef,
    EdgeDef,
    WorkflowDef,
    DataType,
    ToolDef,
)
from fichero.workflows.registry import TOOL_DEFS

logger = logging.getLogger(__name__)


def validate_port_connection(source_port: PortDef, target_port: PortDef) -> bool:
    """Validate that a connection between two ports is compatible.
    
    Args:
        source_port: The source (output) port
        target_port: The target (input) port
        
    Returns:
        True if connection is valid, False otherwise
    """
    # Check if source is output and target is input
    if source_port.port_type != "output":
        logger.warning(f"Source port {source_port.id} is not an output port")
        return False
    
    if target_port.port_type != "input":
        logger.warning(f"Target port {target_port.id} is not an input port")
        return False
    
    # Check data type compatibility
    source_type = source_port.data_type
    target_type = target_port.data_type
    
    # ANY type is compatible with anything
    if source_type == DataType.ANY or target_type == DataType.ANY:
        return True
    
    # Same types are compatible
    if source_type == target_type:
        return True
    
    # Specific type compatibilities
    compatible_types = {
        DataType.FILES: [DataType.FILE],  # Files can connect to single file
        DataType.ARRAY: [DataType.ANY],   # Arrays can connect to any (individual items)
    }
    
    if source_type in compatible_types and target_type in compatible_types[source_type]:
        return True
    
    logger.warning(f"Incompatible data types: {source_type} -> {target_type}")
    return False


def validate_node_connections(node: NodeDef, tool_def: ToolDef | None = None) -> list[str]:
    """Validate all connections for a node.
    
    Args:
        node: The node to validate
        tool_def: Optional tool definition for additional validation
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    # Get tool definition if not provided
    if not tool_def:
        tool_def = TOOL_DEFS.get(node.tool)
        if not tool_def:
            errors.append(f"Unknown tool: {node.tool}")
            return errors
    
    # Check required input ports
    required_inputs = [p for p in tool_def.input_ports if p.required]
    for port in required_inputs:
        # Check if port has a mapping or the port has data
        has_mapping = any(m.port_id == port.id for m in node.input_mappings)
        has_default = port.default is not None
        
        if not has_mapping and not has_default:
            errors.append(f"Required input port '{port.id}' on node '{node.id}' has no mapping or default value")
    
    # Check that all input mappings reference valid ports
    for mapping in node.input_mappings:
        # Check if target port exists
        target_port_exists = any(p.id == mapping.port_id for p in tool_def.input_ports)
        if not target_port_exists:
            errors.append(f"Input mapping references unknown port '{mapping.port_id}' on node '{node.id}'")
    
    return errors


def validate_workflow_connections(workflow: WorkflowDef) -> list[str]:
    """Validate all connections in a workflow.
    
    Args:
        workflow: The workflow to validate
        
    Returns:
        List of error messages (empty if valid)")
    """
    errors = []
    
    # Validate each node
    for node in workflow.nodes:
        node_errors = validate_node_connections(node)
        errors.extend(node_errors)
    
    # Validate each edge
    for edge in workflow.edges:
        # Find source and target nodes
        source_node = workflow.get_node(edge.source)
        target_node = workflow.get_node(edge.target)
        
        if not source_node:
            errors.append(f"Edge references unknown source node: {edge.source}")
            continue
        
        if not target_node:
            errors.append(f"Edge references unknown target node: {edge.target}")
            continue
        
        # Find source and target ports
        source_port = next((p for p in source_node.output_ports if p.id == edge.source_port), None)
        target_port = next((p for p in target_node.input_ports if p.id == edge.target_port), None)
        
        if not source_port:
            errors.append(f"Edge references unknown source port '{edge.source_port}' on node '{edge.source}'")
            continue
        
        if not target_port:
            errors.append(f"Edge references unknown target port '{edge.target_port}' on node '{edge.target}'")
            continue
        
        # Validate connection compatibility
        if not validate_port_connection(source_port, target_port):
            errors.append(f"Invalid connection from {edge.source}.{edge.source_port} to {edge.target}.{edge.target_port}")
    
    return errors


def get_compatible_tools(target_port: PortDef) -> list[ToolDef]:
    """Get tools that can connect to a specific target port.
    
    Args:
        target_port: The target input port
        
    Returns:
        List of compatible tool definitions
    """
    compatible_tools = []
    
    for tool_name, tool_def in TOOL_DEFS.items():
        # Check if this tool has any output ports compatible with target
        for output_port in tool_def.output_ports:
            if validate_port_connection(output_port, target_port):
                compatible_tools.append(tool_def)
                break  # Only need one compatible output per tool
    
    return compatible_tools