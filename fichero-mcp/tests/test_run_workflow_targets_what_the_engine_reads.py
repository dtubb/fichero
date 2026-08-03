"""MCP run_workflow must send the key the ENGINE reads (#4465 #4467 #4480).

Both MCP surfaces built `inputs={"files": [doc_id]}`. Nothing reads `files` —
the Files source node, the CLI and SwiftUI all read `selected_doc_ids` — so
every MCP workflow run resolved to zero documents and completed green. #4467
fixed the ENGINE to refuse that shape rather than succeed at nothing. The MCP
client was never updated to match, so from that moment every `run_workflow`
call 422'd instead: the defect changed shape, from silent to total, and no test
noticed because both trees asserted the shape the SENDER happens to send.

A test that asserts the sender's own output cannot distinguish a working
feature from a broken one — the two agree exactly when it works. So this one
asserts against the RECEIVER: the payload is fed to the engine's real request
model. If the two ever drift again, this fails on the side that matters.
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.workflow_execution.schemas import (
    ExecuteWorkflowRequest,
)


def _payload_for(doc_id: str) -> dict:
    """The inputs dict the MCP tools build, read from the real source.

    Imported rather than retyped so this cannot pass while the tools send
    something else.
    """
    import inspect

    from fichero_mcp import full, simple

    payloads = []
    for module in (simple, full):
        src = inspect.getsource(module.run_workflow)
        assert "input.doc_id" in src, f"{module.__name__} no longer targets doc_id"
        # The tools build one dict literal around doc_id; capture its key.
        key = src.split("{")[1].split(":")[0].strip().strip('"')
        payloads.append({key: [doc_id]})
    return payloads


@pytest.mark.parametrize("index,surface", [(0, "simple"), (1, "full")])
def test_the_engine_accepts_what_the_mcp_tool_sends(index, surface):
    payload = _payload_for("doc-9")[index]
    request = ExecuteWorkflowRequest(workflow_id="wf-1", inputs=payload)
    assert request.selection is not None, (
        f"fichero-mcp {surface} run_workflow sends {payload!r}, which the engine "
        "resolves to NO documents. The run would process nothing"
    )
    assert request.selection.ids == ["doc-9"]


@pytest.mark.parametrize("index,surface", [(0, "simple"), (1, "full")])
def test_it_does_not_send_a_key_the_engine_refuses(index, surface):
    """#4467's refusal is the backstop, not the contract. If a tool sends an
    unread key, the engine raises — better than green-over-nothing, but the
    user sees a 422 on a feature that is simply broken."""
    payload = _payload_for("doc-9")[index]
    assert "files" not in payload, (
        f"fichero-mcp {surface} still sends `files`, which #4467 made the "
        "engine reject outright"
    )
