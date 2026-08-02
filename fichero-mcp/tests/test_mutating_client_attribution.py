"""#4469: MCP mutations prefer the agent account and always tag their surface.

Every mutating tool routes through ``_mutating_client``: the agent session
when one is stored (actor=agent in the audit), otherwise the owner credential
— in which case the X-Fichero-Client tag keeps the audit row truthful about
which surface acted (actor=owner, client=fichero-mcp) instead of silently
impersonating the app.
"""

from unittest.mock import MagicMock, patch

from fichero_mcp import server


def _mock_client():
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


def test_mutating_client_prefers_the_agent_session():
    agent = _mock_client()
    with patch.object(server, "_agent_client", return_value=agent):
        assert server._mutating_client() is agent


def test_mutating_client_falls_back_to_owner_only_when_no_agent_session():
    owner = _mock_client()
    with (
        patch.object(
            server, "_agent_client", side_effect=RuntimeError("no session")
        ),
        patch.object(server, "_client", return_value=owner),
    ):
        assert server._mutating_client() is owner


def test_both_client_builders_tag_the_mcp_surface():
    owner = server._client()
    try:
        assert owner.client_name == "fichero-mcp", (
            "without the tag, an owner-credential MCP mutation audits as the "
            "app — a false record (#4469)"
        )
    finally:
        owner.close()


def test_mutating_tools_route_through_mutating_client():
    """create_note, import, and workflow_run must not use the plain reader."""
    client = _mock_client()
    with patch.object(server, "_mutating_client", return_value=client) as mut:
        for tool, kwargs in [
            (server.fichero_create_note, {"body": "b"}),
            (server.fichero_import, {"path": "/tmp/x.pdf"}),
            (server.fichero_workflow_run, {"workflow_id": "wf", "doc_id": "d"}),
        ]:
            fn = getattr(tool, "fn", tool)
            fn(**kwargs)
    assert mut.call_count == 3
