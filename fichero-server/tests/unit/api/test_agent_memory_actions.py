"""Audited action coverage for agent working-memory notes (#2152)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.system.agent_memory  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, AgentNote, Document, DocType


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def emit_spy(monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def test_create_action_writes_audit_and_emit(db, emit_spy):
    doc = Document(id="doc-action-1", name="Doc", doc_type=DocType.file)
    page = Document(id="page-action-1", name="Page", doc_type=DocType.page)
    db.save(doc)
    db.save(page)

    result = registry.invoke(
        db,
        "agent_memory.create",
        {
            "body": "transparent note",
            "source_anchor": {
                "document_id": doc.id,
                "page_id": page.id,
                "page_label": "3",
                "char_start": 5,
                "char_end": 11,
            },
            "actor": {
                "actor_id": "codex",
                "model_name": "gpt-5",
                "run_id": "run-1",
            },
            "kind": "observation",
            "tags": ["agent"],
        },
        _ctx(),
    )
    assert result.ok

    note_id = result.result["id"]
    note = db.get(AgentNote, note_id)
    assert note is not None
    assert note.source_anchor.page_id == page.id
    assert note.actor.actor_id == "codex"

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.action_name == "agent_memory.create"
    assert audit.target_ids == [note_id]
    assert audit.after["source_anchor"]["document_id"] == doc.id
    assert audit.after["actor"]["run_id"] == "run-1"

    assert emit_spy[-1][1]["type"] == "agent_memory.created"
    assert sorted(emit_spy[-1][1]["document_ids"]) == sorted([doc.id, page.id])


def test_create_action_rejects_missing_anchor_scope(db):
    with pytest.raises(HTTPException) as exc:
        registry.invoke(
            db,
            "agent_memory.create",
            {
                "body": "missing anchor scope",
                "source_anchor": {},
                "actor": {"actor_id": "codex"},
            },
            _ctx(),
        )
    assert "source_anchor must include document_id, page_id, or expediente" in exc.value.detail
