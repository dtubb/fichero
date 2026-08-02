"""#4450 parity: comparisons resolve shipped defaults in ANY library.

The compare endpoints looked a workflow up only in the request's library DB,
so comparing against a default 404'd everywhere except the global library —
"runs in one library but not the other", the exact class Daniel named.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.ai.model_comparison import (
    NodeCompareRequest,
    WorkflowCompareRequest,
    _workflow_from_compare_request,
    _workflow_from_request,
)
from fichero_server.models import Workflow


def _default_row() -> Workflow:
    return Workflow(
        id="default-wf",
        name="Transcribe",
        is_system=True,
        nodes=[{"id": "n1", "tool": "transcribe", "config": {}}],
        edges=[],
    )


@pytest.mark.parametrize(
    ("helper", "make_request"),
    [
        (_workflow_from_request, lambda wid: NodeCompareRequest(workflow_id=wid, node_id="n1")),
        (
            _workflow_from_compare_request,
            lambda wid: WorkflowCompareRequest(workflow_id=wid, doc_id="doc-1"),
        ),
    ],
)
def test_default_workflow_resolves_when_library_db_misses(helper, make_request):
    db = MagicMock()
    db.get.return_value = None  # not a row in THIS library
    with patch(
        "fichero_server.workflows.default_workflows.resolve_default_workflow",
        return_value=_default_row(),
    ):
        wf = helper(make_request("default-wf"), db)
    assert wf.id == "default-wf"
    assert [n.id for n in wf.nodes] == ["n1"]


@pytest.mark.parametrize(
    ("helper", "make_request"),
    [
        (_workflow_from_request, lambda wid: NodeCompareRequest(workflow_id=wid, node_id="n1")),
        (
            _workflow_from_compare_request,
            lambda wid: WorkflowCompareRequest(workflow_id=wid, doc_id="doc-1"),
        ),
    ],
)
def test_truly_unknown_id_still_404s(helper, make_request):
    db = MagicMock()
    db.get.return_value = None
    with patch(
        "fichero_server.workflows.default_workflows.resolve_default_workflow",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as caught:
            helper(make_request("nope"), db)
    assert caught.value.status_code == 404
