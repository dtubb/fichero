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

    def test_file_to_files_is_allowed_from_receiver_behaviour(self):
        """#4478: every files-input consumer coerces a bare string to a
        one-element list before use (process_vision/process_audio/
        video_base/zoom/compare/_doc_lookup/files_tool), and the registry
        has zero file-typed inputs — so file->files is what the runtime
        already does, now permitted by the validator."""
        assert validate_port_connection(
            _port("output", DataType.FILE), _port("input", DataType.FILES)
        )

    def test_the_five_rejected_conversions_stay_rejected(self):
        """Decided per-pair from receiver behaviour (#4478), not type names:
        text receivers silently coerce non-str to "" (a run over nothing,
        the #4467 shape); image ports do not exist in the registry;
        JSON receivers disagree about lists vs dicts. Forbidding is
        recoverable; permitting a conversion the receiver chokes on is
        the #4477 bug moved later."""
        for source, target in [
            ("json", "text"),
            ("array", "json"),
            ("array", "text"),
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


class TestReceiversHandleTheConvertedValue:
    """#4478: an addition to PORT_CONVERSIONS needs proof the RECEIVER
    handles the converted shape — a conversion the validator allows and the
    tool then chokes on just moves the failure later.

    file->files: a single-file value arriving at a files input must become a
    one-element list, at every coercion seam a converted edge can reach."""

    def test_files_source_tool_accepts_a_bare_string(self):
        """files_tool's Priority-1 inputs['files'] path (upstream mapping)."""
        import asyncio
        from unittest.mock import MagicMock

        from fichero_server.workflows.tools.sources import files_tool

        out = asyncio.run(files_tool({"files": "/lib/one.pdf"}, {}, MagicMock()))
        assert out["files"] == ["/lib/one.pdf"]
        assert out["count"] == 1

    def test_doc_lookup_accepts_a_bare_string(self):
        from fichero_server.workflows.tools._doc_lookup import (
            documents_from_state_outputs,
        )

        state = {
            "outputs": {
                "src": {
                    "files": ["/lib/one.pdf"],
                    "documents": [{"id": "d1", "path": "/lib/one.pdf"}],
                }
            }
        }
        docs = documents_from_state_outputs(state, "/lib/one.pdf")
        assert docs and docs[0]["id"] == "d1"

    def test_every_files_consuming_base_coerces_str(self):
        """The coercion the conversion depends on exists in each base that a
        files-typed edge can deliver into. Source-level assertion — if a
        base drops its coercion, permitting file->files becomes unsafe and
        this fails naming the file."""
        from pathlib import Path

        roots = Path("fichero-server/src/fichero_server/workflows/tools")
        for base in ["vision_base.py", "audio_base.py", "video_base.py"]:
            text = (roots / base).read_text(encoding="utf-8")
            assert "isinstance(files, str)" in text, (
                f"{base} no longer coerces a bare string into [files] — "
                "file->files in PORT_CONVERSIONS depends on that coercion"
            )

    def test_no_file_typed_inputs_exist_so_files_is_the_only_route(self):
        """The registry-level fact behind the decision: the four single-file
        outputs can connect to nothing but `any` without this conversion."""
        from fichero_server.workflows.registry import (
            TOOL_DEFS,
            _ensure_tools_loaded,
        )
        from fichero_server.workflows.types import DataType as DT

        _ensure_tools_loaded()
        file_inputs = [
            (name, p.id)
            for name, td in TOOL_DEFS.items()
            for p in td.input_ports
            if p.data_type == DT.FILE
        ]
        assert file_inputs == [], (
            f"file-typed inputs now exist: {file_inputs} — revisit the "
            "#4478 decision notes; the 'only route' argument no longer holds"
        )

    def test_text_receivers_would_silently_empty_a_dict(self):
        """Why json->text stays FORBIDDEN: the receiver turns a dict into
        '' — a run over nothing. This pins the behaviour the decision
        rests on; if a receiver starts raising instead, the pair can be
        reconsidered."""
        from fichero_server.workflows.tools.extract_all import (
            _recover_text_and_records,
        )

        text, records = _recover_text_and_records(
            {"text": {"not": "a string"}, "records": None}, {"outputs": {}}
        )
        assert text == "" and records == []
