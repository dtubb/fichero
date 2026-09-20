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
    # #4983-adjacent fix: `fichero_workflow_run` gained `provider`/`model`
    # run-level overrides on 2026-08-27 (`e90907d0f`), always forwarded as
    # `provider_override`/`model_override` (None when the agent doesn't ask
    # for one) — this test predates that and was never updated. Unrelated
    # to #4961/#4963 (those are Swift app-side bugs: the Library's workflow-
    # row selection and the workflow bar always sending a model override;
    # this MCP tool already does the SAFE thing #4963 wants from the app —
    # no override unless explicitly requested).
    assert kwargs == {
        "force_new": True,
        "skip_cache": False,
        "provider_override": None,
        "model_override": None,
    }
