"""Regression tests for #3455.

`validate_node_connections` only treated a required input port as satisfied
if it had an explicit `input_mapping`. But `to_workflow_def` (runtime.py)
never populates `input_mappings` for workflows loaded from the database — it
relies entirely on edges. So a required port fed by an edge (e.g.
`files-source.files -> transcribe.files`) wrongly failed validation with a
400, even though the edge supplies the data at execution time.
"""

from __future__ import annotations

from fichero.workflows.types import EdgeDef, NodeDef, WorkflowDef
from fichero.workflows.validation import (
    validate_node_connections,
    validate_workflow_connections,
)


class TestEdgeSatisfiesRequiredPort:
    """validate_node_connections: an edge-fed port counts as satisfied."""

    def test_required_port_with_no_mapping_and_no_edge_still_errors(self):
        node = NodeDef(id="transcribe", tool="transcribe", input_mappings=[])
        errors = validate_node_connections(node)
        assert any("files" in e and "no mapping or default" in e for e in errors)

    def test_required_port_fed_by_edge_has_no_error(self):
        node = NodeDef(id="transcribe", tool="transcribe", input_mappings=[])
        errors = validate_node_connections(node, edge_target_ports={"files"})
        assert errors == []

    def test_required_port_with_default_still_ok_without_edge(self):
        """Sanity: a port with a default value doesn't need an edge either."""
        from fichero.workflows.registry import TOOL_DEFS

        tool_def = TOOL_DEFS.get("files")
        assert tool_def is not None
        query_port = next(p for p in tool_def.input_ports if p.id == "query")
        assert query_port.required is False  # optional port, no edge needed

        node = NodeDef(id="files-source", tool="files", input_mappings=[])
        errors = validate_node_connections(node, tool_def=tool_def, edge_target_ports=set())
        assert errors == []


class TestWorkflowValidationConsidersEdges:
    """validate_workflow_connections: edges satisfy required ports end-to-end."""

    def test_workflow_with_edge_fed_required_port_validates(self):
        """files-source.files -> transcribe.files: the exact case from #3455."""
        workflow = WorkflowDef(
            name="Transcribe workflow",
            nodes=[
                NodeDef(id="files-source", tool="files", input_mappings=[]),
                NodeDef(id="transcribe", tool="transcribe", input_mappings=[]),
            ],
            edges=[
                EdgeDef(
                    source="files-source",
                    target="transcribe",
                    source_port="files",
                    target_port="files",
                ),
            ],
        )
        errors = validate_workflow_connections(workflow)
        assert errors == [], f"Unexpected validation errors: {errors}"

    def test_workflow_with_missing_edge_and_no_default_still_errors(self):
        """No edge into the required port and no default -> still an error."""
        workflow = WorkflowDef(
            name="Broken transcribe workflow",
            nodes=[
                NodeDef(id="files-source", tool="files", input_mappings=[]),
                NodeDef(id="transcribe", tool="transcribe", input_mappings=[]),
            ],
            edges=[],
        )
        errors = validate_workflow_connections(workflow)
        assert any(
            "files" in e and "no mapping or default" in e for e in errors
        ), f"Expected a required-port error, got: {errors}"

    def test_workflow_edge_to_wrong_port_still_errors(self):
        """An edge that targets a different port doesn't satisfy the required one."""
        workflow = WorkflowDef(
            name="Mis-wired transcribe workflow",
            nodes=[
                NodeDef(id="files-source", tool="files", input_mappings=[]),
                NodeDef(id="transcribe", tool="transcribe", input_mappings=[]),
            ],
            edges=[
                EdgeDef(
                    source="files-source",
                    target="transcribe",
                    source_port="files",
                    target_port="not-a-real-port",
                ),
            ],
        )
        errors = validate_workflow_connections(workflow)
        assert any(
            "files" in e and "no mapping or default" in e for e in errors
        ), f"Expected a required-port error, got: {errors}"
