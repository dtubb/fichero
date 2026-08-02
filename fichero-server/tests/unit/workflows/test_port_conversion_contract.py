"""#4477: ONE port-conversion table — engine-owned, served, save-enforced.

The node editor kept a hand-written copy of edge legality and drifted to six
conversions the engine rejects: edges drew fine, saved fine, and died at run
time. The contract now: ``PORT_CONVERSIONS`` is the only table,
``validate_port_connection`` reads it, ``GET /api/workflows/tools`` serves it
(the canvas derives from the served copy), and save 422s an edge the engine
would refuse to execute.
"""

from __future__ import annotations

from itertools import product

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.workflow.workflows import (
    create_workflow_impl,
    list_workflow_tools,
)
from fichero_server.workflows.types import DataType, EdgeDef, NodeDef, PortDef, WorkflowDef
from fichero_server.workflows.validation import (
    PORT_CONVERSIONS,
    port_conversion_table,
    validate_edge_type_errors,
    validate_port_connection,
)


def _port(port_type: str, data_type: DataType) -> PortDef:
    return PortDef(id="p", name="p", port_type=port_type, data_type=data_type)


class TestTheTableIsTheBehaviour:
    """The exported table and the validator can never disagree."""

    def test_every_pair_matches_the_table_exactly(self):
        for source, target in product(DataType, DataType):
            expected = (
                source == DataType.ANY
                or target == DataType.ANY
                or source == target
                or target in PORT_CONVERSIONS.get(source, ())
            )
            actual = validate_port_connection(
                _port("output", source), _port("input", target)
            )
            assert actual == expected, f"{source.value} -> {target.value}"

    def test_the_old_editor_conversions_stay_rejected(self):
        """The canvas's five extra conversions were optimism, not design —
        resolving the divergence by widening the engine is explicitly the
        wrong fix (#4477). If one becomes desirable, it gets its own issue."""
        for source, target in [
            ("json", "text"),
            ("array", "json"),
            ("array", "text"),
            ("file", "files"),
            ("image", "file"),
            ("image", "files"),
        ]:
            assert not validate_port_connection(
                _port("output", DataType(source)), _port("input", DataType(target))
            ), f"{source} -> {target} must stay engine-rejected"

    def test_wire_form_mirrors_the_table(self):
        served = port_conversion_table()
        assert served == {
            s.value: [t.value for t in ts] for s, ts in PORT_CONVERSIONS.items()
        }
        assert served, "an empty served table would silently strip files->file"


class TestTheRouteServesIt:
    @pytest.mark.asyncio
    async def test_tools_response_carries_the_conversion_table(self):
        response = await list_workflow_tools()
        assert response.conversions == port_conversion_table(), (
            "the canvas derives edge legality from this field; serving "
            "anything but THE table recreates the two-copies defect"
        )


def _two_node_workflow(source_type: DataType, target_type: DataType) -> WorkflowDef:
    """Synthetic tools (unknown to the registry) keep their inline ports."""
    return WorkflowDef(
        name="t",
        nodes=[
            NodeDef(
                id="a",
                tool="synthetic-source",
                output_ports=[
                    PortDef(id="out", name="out", port_type="output", data_type=source_type)
                ],
            ),
            NodeDef(
                id="b",
                tool="synthetic-sink",
                input_ports=[
                    PortDef(id="in", name="in", port_type="input", data_type=target_type)
                ],
            ),
        ],
        edges=[EdgeDef(source="a", source_port="out", target="b", target_port="in")],
    )


class TestSaveRefusesWhatExecutionWouldRefuse:
    def test_incompatible_edge_is_named_by_the_validator(self):
        errors = validate_edge_type_errors(
            _two_node_workflow(DataType.IMAGE, DataType.FILES)
        )
        assert len(errors) == 1
        assert "image" in errors[0] and "files" in errors[0]

    def test_compatible_and_convertible_edges_pass(self):
        assert validate_edge_type_errors(
            _two_node_workflow(DataType.FILES, DataType.FILE)
        ) == []
        assert validate_edge_type_errors(
            _two_node_workflow(DataType.TEXT, DataType.TEXT)
        ) == []

    def test_unknown_ports_are_left_for_execution_time(self):
        """Drafts keep saving: a dangling edge is a mid-edit state, an
        incompatible edge between known ports is not."""
        wf = _two_node_workflow(DataType.IMAGE, DataType.FILES)
        wf.edges[0].target_port = "no-such-port"
        assert validate_edge_type_errors(wf) == []

    def test_create_impl_422s_an_engine_rejected_edge(self):
        with pytest.raises(HTTPException) as caught:
            create_workflow_impl(object(), _two_node_workflow(DataType.IMAGE, DataType.FILES))
        assert caught.value.status_code == 422
        assert "Incompatible connection" in str(caught.value.detail)


class TestPresetJsonValidatesDirectly:
    """#4477 side-finding: presets carry ``version: 1`` (int) but the field
    is str, so direct ``model_validate`` of preset dicts — which the
    sub-workflow JSON fallback performs — threw on every such preset."""

    def test_int_version_coerces(self):
        wf = WorkflowDef.model_validate({"name": "t", "version": 1})
        assert wf.version == "1"

    def test_every_shipped_preset_validates_as_a_workflowdef(self):
        from fichero_server.workflows.default_workflows import _load_preset_files

        presets = list(_load_preset_files())
        assert len(presets) >= 30, "preset discovery went blind"
        for preset in presets:
            WorkflowDef.model_validate(preset)  # must not raise
