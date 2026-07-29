"""Route tests for agent working-memory notes (#2152)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fichero_server.api.main import app
from fichero_server.db import db_manager
from fichero_server.models import ActionAudit, AgentNote, Document, DocType


def _payload(document_id: str, page_id: str) -> dict:
    return {
        "body": "Interpretative working note",
        "source_anchor": {
            "document_id": document_id,
            "page_id": page_id,
            "expediente": "exp-42",
            "page_label": "Page 7",
            "char_start": 12,
            "char_end": 24,
        },
        "actor": {
            "actor_id": "codex",
            "model_name": "gpt-5",
            "run_id": "run-2152",
        },
        "kind": "observation",
        "tags": ["working-memory", "visible"],
    }


class TestAgentMemoryRoutes:
    def test_create_get_list_update_delete_round_trip(self, client, db):
        doc = Document(id="doc-agent-1", name="Doc", doc_type=DocType.file)
        page = Document(id="page-agent-1", name="Page 1", doc_type=DocType.page)
        db.save(doc)
        db.save(page)

        create = client.post("/api/agent-memory", json=_payload(doc.id, page.id))
        assert create.status_code == 200
        created = create.json()
        note_id = created["id"]
        assert created["source_anchor"]["document_id"] == doc.id
        assert created["source_anchor"]["page_id"] == page.id
        assert created["actor"]["actor_id"] == "codex"
        assert created["actor"]["run_id"] == "run-2152"

        audit_rows = db.all(ActionAudit)
        assert any(row.action_name == "agent_memory.create" for row in audit_rows)

        get_resp = client.get(f"/api/agent-memory/{note_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == note_id

        list_resp = client.get(
            "/api/agent-memory",
            params={
                "actor_id": "codex",
                "kind": "observation",
                "source_document_id": doc.id,
                "page_id": page.id,
                "expediente": "exp-42",
            },
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["count"] == 1
        assert listed["items"][0]["id"] == note_id

        patch = client.patch(
            f"/api/agent-memory/{note_id}",
            json={
                "body": "Updated interpretative note",
                "kind": "hypothesis",
                "tags": ["updated"],
                "actor": {
                    "actor_id": "codex-review",
                    "model_name": "gpt-5",
                    "run_id": "run-2152b",
                },
            },
        )
        assert patch.status_code == 200
        updated = patch.json()
        assert updated["body"] == "Updated interpretative note"
        assert updated["kind"] == "hypothesis"
        assert updated["tags"] == ["updated"]
        assert updated["actor"]["actor_id"] == "codex-review"

        delete = client.delete(f"/api/agent-memory/{note_id}")
        assert delete.status_code == 204
        assert db.get(AgentNote, note_id) is None
        assert client.get(f"/api/agent-memory/{note_id}").status_code == 404

    def test_missing_source_anchor_is_rejected(self, client):
        create = client.post(
            "/api/agent-memory",
            json={
                "body": "No provenance",
                "actor": {"actor_id": "codex"},
            },
        )
        assert create.status_code == 422

    def test_cross_library_isolation(self, tmp_path):
        def _make_library(name: str) -> Path:
            package = tmp_path / f"{name}.fichero"
            package.mkdir()
            (package / "lance").mkdir()
            (package / "storage").mkdir()
            (package / "files").mkdir()
            db_manager.get_database(package)
            return package

        lib_a = _make_library("a")
        lib_b = _make_library("b")

        db_a = db_manager.get_database(lib_a)
        db_b = db_manager.get_database(lib_b)
        db_a.save(Document(id="doc-a", name="Doc A", doc_type=DocType.file))
        db_a.save(Document(id="page-a", name="Page A", doc_type=DocType.page))
        db_b.save(Document(id="doc-b", name="Doc B", doc_type=DocType.file))
        db_b.save(Document(id="page-b", name="Page B", doc_type=DocType.page))

        client_a = TestClient(app, headers={"X-Fichero-Library-Path": str(lib_a)})
        client_b = TestClient(app, headers={"X-Fichero-Library-Path": str(lib_b)})

        try:
            create_a = client_a.post("/api/agent-memory", json=_payload("doc-a", "page-a"))
            assert create_a.status_code == 200
            note_id = create_a.json()["id"]

            list_a = client_a.get("/api/agent-memory")
            assert list_a.status_code == 200
            assert list_a.json()["count"] == 1

            list_b = client_b.get("/api/agent-memory")
            assert list_b.status_code == 200
            assert list_b.json()["count"] == 0
            assert client_b.get(f"/api/agent-memory/{note_id}").status_code == 404
        finally:
            client_a.close()
            client_b.close()
            db_manager.close_all()
