"""Workspace MCP tools delegate to the audited action registry (#3569)."""

from __future__ import annotations

import pytest

from fichero import accounts, authz, mcp_server
from fichero.actions.registry import ActionContext, registry
from fichero.knowledge_models import KnowledgeClaim
from fichero.models import ActionAudit, DocType, Document


class _ActionClient:
    """In-process stand-in for the MCP server's audited HTTP endpoint."""

    def __init__(self, db, actor: str = "agent"):
        self.db = db
        self.actor = actor

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def request(self, method, path, *, json):
        assert (method, path) == ("POST", "/api/actions/invoke")
        result = registry.invoke(
            self.db,
            json["name"],
            json["params"],
            ActionContext(actor=self.actor, library_path=str(self.db.path.parent)),
        )
        return {"ok": result.ok, "audit_id": result.audit_id, "result": result.result}


def _workspace(db) -> Document:
    workspace = Document(
        name="Agent workspace",
        doc_type=DocType.folder,
        node_kind="workspace",
        is_workspace=True,
        metadata={"workspace_kind": "agent"},
    )
    db.save(workspace)
    return workspace


@pytest.mark.parametrize(
    ("tool", "action", "prepare", "arguments", "expected_role"),
    [
        (
            mcp_server.fichero_workspace_add_source,
            "workspace.add_source",
            lambda db: Document(name="Source"),
            lambda workspace, target: (workspace.id, target.id),
            "agent_source",
        ),
        (
            mcp_server.fichero_workspace_remove_source,
            "workspace.remove_source",
            lambda db: Document(name="Source"),
            lambda workspace, target: (workspace.id, target.id),
            None,
        ),
        (
            mcp_server.fichero_workspace_surface_claim,
            "workspace.surface_claim",
            lambda db: KnowledgeClaim(text="The petition was filed in 1844."),
            lambda workspace, target: (workspace.id, target.id),
            "surfaced_claim",
        ),
        (
            mcp_server.fichero_workspace_add_note,
            "workspace.add_note",
            lambda db: None,
            lambda workspace, target: (workspace.id, "Check the ledger date."),
            "agent_note",
        ),
    ],
)
def test_workspace_mcp_tools_mutate_and_audit(
    db, monkeypatch, tool, action, prepare, arguments, expected_role
):
    workspace = _workspace(db)
    target = prepare(db)
    if target is not None:
        db.save(target)
    if action == "workspace.remove_source":
        registry.invoke(
            db,
            "workspace.add_source",
            {"workspace_id": workspace.id, "document_id": target.id},
            ActionContext(actor="agent", library_path=str(db.path.parent)),
        )
    monkeypatch.setattr(mcp_server, "_agent_client", lambda: _ActionClient(db))

    tool(*arguments(workspace, target))

    items = db.get(Document, workspace.id).curated_items
    assert (items and items[0]["role"] == expected_role) if expected_role else not items
    audit = sorted(db.all(ActionAudit), key=lambda row: row.created_at)[-1]
    assert (audit.action_name, audit.actor) == (action, "agent")


def test_workspace_mcp_tool_denies_unauthorized_actor(db, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    agent = app_db.create_user(
        username="agent", display_name="Agent", password_hash=accounts.hash_password("agent")
    )
    viewer = app_db.create_user(
        username="viewer", display_name="Viewer", password_hash=accounts.hash_password("viewer")
    )
    library_path = authz.normalize_library_path(str(db.path.parent))
    app_db.set_library_role(user_id=agent.id, library_path=library_path, role="editor")
    app_db.set_library_role(user_id=viewer.id, library_path=library_path, role="viewer")
    workspace = _workspace(db)
    source = Document(name="Source")
    db.save(source)
    monkeypatch.setattr(
        mcp_server, "_agent_client", lambda: _ActionClient(db, actor="viewer")
    )

    with pytest.raises(authz.AuthorizationError):
        mcp_server.fichero_workspace_add_source(workspace.id, source.id)
