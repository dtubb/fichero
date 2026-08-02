"""#4467: fichero_workflow_run must target via `selected_doc_ids`.

The tool used to send `inputs={"files": [doc_id]}`, which no node reads from
execute inputs — the engine reported the run completed while processing zero
documents. This pins the request shape to the one the Files-source node (and
the CLI, and SwiftUI) actually read.
"""

from unittest.mock import MagicMock, patch

from fichero_mcp import server


def test_workflow_run_sends_selected_doc_ids():
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)

    with patch.object(server, "_client", return_value=client):
        # FastMCP wraps the function; call the underlying callable.
        fn = getattr(server.fichero_workflow_run, "fn", server.fichero_workflow_run)
        fn(workflow_id="wf-1", doc_id="doc-1", force_new=True, skip_cache=False)

    args, kwargs = client.run_workflow.call_args
    assert args[0] == "wf-1"
    assert args[1] == {"selected_doc_ids": ["doc-1"]}, (
        "targets must ride under selected_doc_ids — inputs['files'] is read "
        "by nothing and the run completes green on zero documents (#4467)"
    )
    assert kwargs == {"force_new": True, "skip_cache": False}
