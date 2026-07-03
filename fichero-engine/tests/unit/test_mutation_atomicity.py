"""Failure-injection guards for audited mutation atomicity.

These tests pin the write-path integrity of the audited mutation sweep:
when a mutation fails during storage, audit persistence, or emit, the system
must not leave behind torn state.

The current registry contract treats the generic post-audit emit as
best-effort, but several domain actions still emit inside the action handler
before the audit row is written. Those paths are the ones this file probes.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import fichero.api.routes.documents  # noqa: F401
import fichero.api.routes.entities  # noqa: F401
import fichero.api.routes.notes  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.db import Database
from fichero.knowledge_models import KnowledgeEntity, Note
from fichero.models import ActionAudit, DocType, Document


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _emit_spy(monkeypatch) -> list[tuple[tuple, dict]]:
    calls: list[tuple[tuple, dict]] = []

    def _record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("fichero.api.routes.notes.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.documents.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.entities.emit_change", _record)
    monkeypatch.setattr("fichero.api.change_stream.emit_change", _record)
    return calls


def _count_audits(db: Database, action_name: str) -> int:
    return len([row for row in db.all(ActionAudit) if row.action_name == action_name])


def _note_count(db: Database) -> int:
    return len(db.all(Note))


def _document_count(db: Database) -> int:
    return len(db.all(Document))


def _entity_count(db: Database) -> int:
    return len(db.all(KnowledgeEntity))


def _invoke_note_create(db: Database) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _note_count(db)
    before_audits = _count_audits(db, "note.create")

    def _call():
        return registry.invoke(
            db,
            "note.create",
            {"title": "Atomicity Note", "body": "body"},
            _ctx(),
        )

    def _assert_rolled_back():
        assert _note_count(db) == before_count
        assert _count_audits(db, "note.create") == before_audits

    return _call, _assert_rolled_back, "note.create"


def _assert_note_create_committed(
    db: Database, before_count: int, before_audits: int
) -> None:
    assert _note_count(db) == before_count + 1
    assert _count_audits(db, "note.create") == before_audits + 1


def _invoke_document_create(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _document_count(db)
    before_audits = _count_audits(db, "document.create")

    def _call():
        return registry.invoke(db, "document.create", {"name": "Atomic Doc"}, _ctx())

    def _assert_rolled_back():
        assert _document_count(db) == before_count
        assert _count_audits(db, "document.create") == before_audits

    return _call, _assert_rolled_back, "document.create"


def _assert_document_create_committed(
    db: Database, before_count: int, before_audits: int
) -> None:
    assert _document_count(db) == before_count + 1
    assert _count_audits(db, "document.create") == before_audits + 1


def _invoke_entity_create(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _entity_count(db)
    before_audits = _count_audits(db, "entity.create")

    def _call():
        return registry.invoke(
            db,
            "entity.create",
            {"canonical_name": "Atomic Entity"},
            _ctx(),
        )

    def _assert_rolled_back():
        assert _entity_count(db) == before_count
        assert _count_audits(db, "entity.create") == before_audits

    return _call, _assert_rolled_back, "entity.create"


def _assert_entity_create_committed(
    db: Database, before_count: int, before_audits: int
) -> None:
    assert _entity_count(db) == before_count + 1
    assert _count_audits(db, "entity.create") == before_audits + 1


def _invoke_document_move(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    source = Document(name="Source", doc_type=DocType.folder)
    target = Document(name="Target", doc_type=DocType.folder)
    doc = Document(name="Move Me", parent_id=source.id)
    db.save(source)
    db.save(target)
    db.save(doc)
    before_audits = _count_audits(db, "document.move")
    before_parent = source.id

    def _call():
        return registry.invoke(
            db,
            "document.move",
            {"doc_id": doc.id, "parent_id": target.id},
            _ctx(),
        )

    def _assert_rolled_back():
        reloaded = db.get(Document, doc.id)
        assert reloaded is not None
        assert reloaded.parent_id == before_parent
        assert _count_audits(db, "document.move") == before_audits

    return _call, _assert_rolled_back, "document.move"


def _assert_document_move_committed(
    db: Database, doc_id: str, target_parent_id: str, before_audits: int
) -> None:
    reloaded = db.get(Document, doc_id)
    assert reloaded is not None
    assert reloaded.parent_id == target_parent_id
    assert _count_audits(db, "document.move") == before_audits + 1


def _emit_note_create_case(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _note_count(db)
    before_audits = _count_audits(db, "note.create")

    def _call():
        return registry.invoke(
            db,
            "note.create",
            {"title": "Atomicity Note", "body": "body"},
            _ctx(),
        )

    def _assert_committed():
        _assert_note_create_committed(db, before_count, before_audits)

    return _call, _assert_committed, "fichero.api.routes.notes.emit_change"


def _emit_document_create_case(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _document_count(db)
    before_audits = _count_audits(db, "document.create")

    def _call():
        return registry.invoke(db, "document.create", {"name": "Atomic Doc"}, _ctx())

    def _assert_committed():
        _assert_document_create_committed(db, before_count, before_audits)

    return _call, _assert_committed, "fichero.api.routes.documents.emit_change"


def _emit_entity_create_case(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    before_count = _entity_count(db)
    before_audits = _count_audits(db, "entity.create")

    def _call():
        return registry.invoke(
            db,
            "entity.create",
            {"canonical_name": "Atomic Entity"},
            _ctx(),
        )

    def _assert_committed():
        _assert_entity_create_committed(db, before_count, before_audits)

    return _call, _assert_committed, "fichero.api.routes.entities.emit_change"


def _emit_document_move_case(
    db: Database,
) -> tuple[Callable[[], object], Callable[[], None], str]:
    source = Document(name="Source", doc_type=DocType.folder)
    target = Document(name="Target", doc_type=DocType.folder)
    doc = Document(name="Move Me", parent_id=source.id)
    db.save(source)
    db.save(target)
    db.save(doc)
    before_audits = _count_audits(db, "document.move")

    def _call():
        return registry.invoke(
            db,
            "document.move",
            {"doc_id": doc.id, "parent_id": target.id},
            _ctx(),
        )

    def _assert_committed():
        _assert_document_move_committed(db, doc.id, target.id, before_audits)

    return _call, _assert_committed, "fichero.api.routes.documents.emit_change"


@pytest.mark.parametrize(
    ("label", "builder", "target_type_name"),
    [
        ("note.create", _invoke_note_create, "Note"),
        ("document.create", _invoke_document_create, "Document"),
        ("entity.create", _invoke_entity_create, "KnowledgeEntity"),
        ("document.move", _invoke_document_move, "Document"),
    ],
)
def test_storage_failure_rolls_back_without_audit_or_emit(
    label: str,
    builder: Callable[[Database], tuple[Callable[[], object], Callable[[], None], str]],
    target_type_name: str,
    db,
    monkeypatch,
):
    emit_calls = _emit_spy(monkeypatch)
    call, assert_rolled_back, _action_name = builder(db)
    original_save = Database.save

    def _boom(self, obj, auto_embed=False):
        if type(obj).__name__ == target_type_name:
            raise RuntimeError(f"boom storage {label}")
        return original_save(self, obj, auto_embed=auto_embed)

    monkeypatch.setattr(Database, "save", _boom)

    with pytest.raises(RuntimeError, match=f"boom storage {label}"):
        call()

    assert_rolled_back()
    assert emit_calls == []


@pytest.mark.parametrize(
    ("label", "builder"),
    [
        ("note.create", _invoke_note_create),
        ("document.create", _invoke_document_create),
        ("entity.create", _invoke_entity_create),
        ("document.move", _invoke_document_move),
    ],
)
def test_audit_failure_does_not_leave_persisted_state_or_emit(
    label: str,
    builder: Callable[[Database], tuple[Callable[[], object], Callable[[], None], str]],
    db,
    monkeypatch,
):
    emit_calls = _emit_spy(monkeypatch)
    call, assert_rolled_back, _action_name = builder(db)

    def _boom(*args, **kwargs):
        raise RuntimeError(f"boom audit {label}")

    monkeypatch.setattr("fichero.actions.audit_chain.save_chained_audit", _boom)

    with pytest.raises(RuntimeError, match=f"boom audit {label}"):
        call()

    assert_rolled_back()
    assert emit_calls == []


@pytest.mark.parametrize(
    ("label", "builder"),
    [
        ("note.create", _emit_note_create_case),
        ("document.create", _emit_document_create_case),
        ("entity.create", _emit_entity_create_case),
        ("document.move", _emit_document_move_case),
    ],
)
def test_emit_failure_is_best_effort_after_commit(
    label: str,
    builder: Callable[[Database], tuple[Callable[[], object], Callable[[], None], str]],
    db,
    monkeypatch,
):
    call, assert_committed, emit_symbol = builder(db)

    def _boom(*args, **kwargs):
        raise RuntimeError(f"boom emit {label}")

    monkeypatch.setattr(emit_symbol, _boom)

    result = call()
    assert result.ok is True
    assert_committed()
