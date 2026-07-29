"""Tests for files/folder query port required=False fix (#1118/#1179).

Before this fix the "Query" input port on the `files` and `collection` tools
had `required=True` (the PortDef default).  `validate_node_connections` would
emit an error for any workflow node using those tools that did not wire up the
Query port, which is the normal case — the query port is optional filter sugar,
not a mandatory input.

After the fix both ports carry `required=False`, so the validator produces no
errors for nodes that leave the Query port unmapped.
"""

from __future__ import annotations


from fichero_server.workflows.types import NodeDef
from fichero_server.workflows.validation import validate_node_connections


class TestFilesToolQueryPortOptional:
    """files tool: Query port must be optional so validation passes without it."""

    def test_files_node_with_no_query_mapping_has_no_errors(self):
        """A files tool node with no input mappings must validate cleanly."""
        node = NodeDef(tool="files", input_mappings=[])
        errors = validate_node_connections(node)
        assert errors == [], (
            f"Unexpected validation errors for files node: {errors}"
        )

    def test_files_node_query_port_is_not_required(self):
        """Confirm the files tool's Query port is explicitly required=False."""
        from fichero_server.workflows.registry import TOOL_DEFS

        tool_def = TOOL_DEFS.get("files")
        assert tool_def is not None, "files tool must be registered"

        query_ports = [p for p in tool_def.input_ports if p.id == "query"]
        assert query_ports, "files tool must have a query input port"
        query_port = query_ports[0]
        assert query_port.required is False, (
            f"files tool Query port should be required=False, got required={query_port.required}"
        )

    def test_files_node_with_query_mapping_also_validates(self):
        """A files node WITH a query mapping also passes validation (sanity)."""
        from fichero_server.workflows.types import InputMapping

        node = NodeDef(
            tool="files",
            input_mappings=[
                InputMapping(port_id="query", source_path="$.inputs.search_query"),
            ],
        )
        errors = validate_node_connections(node)
        assert errors == []


class TestFolderToolQueryPortOptional:
    """folder tool: Query port must be optional so validation passes without it."""

    def test_folder_node_with_no_query_mapping_has_no_errors(self):
        """A folder tool node with no input mappings must validate cleanly."""
        node = NodeDef(tool="folder", input_mappings=[])
        errors = validate_node_connections(node)
        assert errors == [], (
            f"Unexpected validation errors for folder node: {errors}"
        )

    def test_folder_node_query_port_is_not_required(self):
        """Confirm the folder tool's Query port is explicitly required=False."""
        from fichero_server.workflows.registry import TOOL_DEFS

        tool_def = TOOL_DEFS.get("folder")
        assert tool_def is not None, "folder tool must be registered"

        query_ports = [p for p in tool_def.input_ports if p.id == "query"]
        assert query_ports, "folder tool must have a query input port"
        query_port = query_ports[0]
        assert query_port.required is False, (
            f"folder tool Query port should be required=False, "
            f"got required={query_port.required}"
        )

    def test_folder_node_with_query_mapping_also_validates(self):
        """A folder node WITH a query mapping also passes validation (sanity)."""
        from fichero_server.workflows.types import InputMapping

        node = NodeDef(
            tool="folder",
            input_mappings=[
                InputMapping(port_id="query", source_path="$.inputs.q"),
            ],
        )
        errors = validate_node_connections(node)
        assert errors == []


class TestWorkflowValidationWithSourceNodes:
    """End-to-end: a workflow containing files/collection nodes validates cleanly."""

    def test_workflow_with_files_node_passes_validation(self):
        """WorkflowDef containing a bare files node produces no validation errors."""
        from fichero_server.workflows.types import WorkflowDef
        from fichero_server.workflows.validation import validate_workflow_connections

        workflow = WorkflowDef(
            name="Test Workflow",
            nodes=[NodeDef(tool="files", input_mappings=[])],
            edges=[],
        )
        errors = validate_workflow_connections(workflow)
        port_errors = [e for e in errors if "query" in e.lower() or "required" in e.lower()]
        assert port_errors == [], (
            f"Unexpected port-related errors in workflow validation: {port_errors}"
        )

    def test_workflow_with_folder_node_passes_validation(self):
        """WorkflowDef containing a bare folder node produces no validation errors."""
        from fichero_server.workflows.types import WorkflowDef
        from fichero_server.workflows.validation import validate_workflow_connections

        workflow = WorkflowDef(
            name="Folder Workflow",
            nodes=[NodeDef(tool="folder", input_mappings=[])],
            edges=[],
        )
        errors = validate_workflow_connections(workflow)
        port_errors = [e for e in errors if "query" in e.lower() or "required" in e.lower()]
        assert port_errors == [], (
            f"Unexpected port-related errors in folder workflow validation: {port_errors}"
        )
