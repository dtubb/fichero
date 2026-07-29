"""#2528: workflow import has parity with export — it validates against the
typed NodeDef/EdgeDef models, fails loud on a bad file (no silent partial
import), and round-trips with export to an identical graph.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException


def _make_workflow(db):
    """Create a stored workflow and return (workflow, export_payload dict)."""
    from fichero_server.api.routes.workflows import create_workflow_impl
    from fichero_server.workflows.types import WorkflowDef, NodeDef, EdgeDef

    wf = create_workflow_impl(
        db,
        WorkflowDef(
            id="wf-imp",
            name="Round Trip",
            description="export→import identical",
            nodes=[
                NodeDef(id="n1", tool="transcribe"),
                NodeDef(id="n2", tool="describe"),
            ],
            edges=[EdgeDef(source="n1", target="n2")],
        ),
    )
    # The export endpoint emits the raw stored node/edge dicts verbatim.
    export_payload = {
        "name": wf.name,
        "description": wf.description,
        "provider": wf.provider,
        "model": wf.model,
        "nodes": wf.nodes,
        "edges": wf.edges,
    }
    return wf, export_payload


class TestImportParity:
    def test_export_import_round_trips_identical(self, db):
        from fichero_server.api.routes.workflows import import_workflow_impl

        _, payload = _make_workflow(db)
        imported = import_workflow_impl(db, name="", description="", workflow_data=payload)

        assert imported.nodes == payload["nodes"]
        assert imported.edges == payload["edges"]
        assert imported.name == "Round Trip"

    def test_missing_nodes_or_edges_fails_loud(self, db):
        from fichero_server.api.routes.workflows import import_workflow_impl

        with pytest.raises(HTTPException) as exc:
            import_workflow_impl(db, name="", description="", workflow_data={"nodes": []})
        assert exc.value.status_code == 400

    def test_malformed_node_fails_loud_and_persists_nothing(self, db):
        from fichero_server.api.routes.workflows import import_workflow_impl
        from fichero_server.models import Workflow

        before = len(db.query(Workflow))
        bad = {"nodes": ["not-a-node-dict"], "edges": []}
        with pytest.raises(HTTPException) as exc:
            import_workflow_impl(db, name="", description="", workflow_data=bad)
        assert exc.value.status_code == 400
        assert "node[0]" in exc.value.detail
        # No silent partial import — nothing was saved.
        assert len(db.query(Workflow)) == before

    def test_malformed_edge_fails_loud(self, db):
        from fichero_server.api.routes.workflows import import_workflow_impl

        bad = {"nodes": [{"id": "n1", "tool": "transcribe"}], "edges": ["bad-edge"]}
        with pytest.raises(HTTPException) as exc:
            import_workflow_impl(db, name="", description="", workflow_data=bad)
        assert exc.value.status_code == 400
        assert "edge[0]" in exc.value.detail

    def test_nodes_not_a_list_fails_loud(self, db):
        from fichero_server.api.routes.workflows import import_workflow_impl

        with pytest.raises(HTTPException) as exc:
            import_workflow_impl(
                db, name="", description="", workflow_data={"nodes": {}, "edges": []}
            )
        assert exc.value.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
