"""proto.template.per-scope-column-choice: narrowing a scope's columns is a saved view, not a prototype change."""

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue


def _proto(db, key, attrs, parent=None):
    db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key=key, label=key,
                                parent_key=parent, attributes=attrs))


def _scope(db):
    _proto(db, "tbase", {"title": {"type": "text", "order": 1}})
    _proto(db, "tletter", {"sender": {"type": "text", "order": 2}}, parent="tbase")
    _proto(db, "tcourt", {"judge": {"type": "text", "order": 2}}, parent="tbase")
    box = Document(id="scope", name="scope", path="/scope", doc_type=DocType.folder)
    db.save(box)
    for i, kind in enumerate(("tletter", "tcourt")):
        db.save(Document(id=f"r{i}", name=f"r{i}", path=f"/r{i}", doc_type=DocType.folder, parent_id="scope",
                         prototype_key=kind, sequence=i))
    return box


def _keys(response):
    return [c["key"] for c in response.json()["columns"]]


def test_default_is_the_union(client, db):
    _scope(db)
    r = client.get("/api/documents/scope/template")
    assert r.status_code == 200
    assert _keys(r) == ["title", "sender", "judge"] and r.json()["mixed"] is True


def test_choice_narrows_the_scope_and_is_saved_on_it_not_on_a_prototype(client, db):
    _scope(db)
    r = client.put("/api/documents/scope/column-choice", json={"hide": ["title"]})
    assert r.status_code == 200 and _keys(r) == ["sender", "judge"]
    assert _keys(client.get("/api/documents/scope/template")) == ["sender", "judge"]  # persisted
    only = client.put("/api/documents/scope/column-choice", json={"only_kind": "tcourt"})
    assert _keys(only) == ["title", "judge"]
    protos = {v.key: v.attributes for v in db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype)}
    assert set(protos["tbase"]) == {"title"}  # no prototype changed


def test_clearing_returns_to_the_union(client, db):
    _scope(db)
    client.put("/api/documents/scope/column-choice", json={"hide": ["title"]})
    r = client.delete("/api/documents/scope/column-choice")
    assert _keys(r) == ["title", "sender", "judge"] and r.json()["choice"] is None


def test_undo_restores_the_previous_choice(client, db):
    _scope(db)
    ctx = ActionContext(actor="tester", library_path="/tmp/library.fichero")
    forward = registry.invoke(db, "document.set_column_choice",
                              {"doc_id": "scope", "choice": {"hide": ["title"]}}, ctx)
    assert _keys(client.get("/api/documents/scope/template")) == ["sender", "judge"]
    undo = client.post(f"/api/actions/audit/{forward.audit_id}/undo")
    assert undo.status_code == 200, undo.text
    assert _keys(client.get("/api/documents/scope/template")) == ["title", "sender", "judge"]


def test_the_answer_names_the_audit_row_and_it_undoes_through_the_route(client, db):
    _scope(db)
    put = client.put("/api/documents/scope/column-choice", json={"hide": ["title"]})
    assert put.status_code == 200 and put.json()["audit_id"]
    assert client.get("/api/documents/scope/template").json().get("audit_id") is None
    cleared = client.delete("/api/documents/scope/column-choice")
    assert cleared.json()["audit_id"] and cleared.json()["audit_id"] != put.json()["audit_id"]
    assert client.post(f"/api/actions/audit/{cleared.json()['audit_id']}/undo").status_code == 200
    assert _keys(client.get("/api/documents/scope/template")) == ["sender", "judge"]


def test_unknown_scope_is_404_on_all_three_routes(client):
    assert client.get("/api/documents/nope/template").status_code == 404
    assert client.put("/api/documents/nope/column-choice", json={"hide": ["x"]}).status_code == 404
    assert client.delete("/api/documents/nope/column-choice").status_code == 404
