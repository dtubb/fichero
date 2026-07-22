from __future__ import annotations

from fichero.security import accounts
from fichero.security import authz
from fichero.models import Document, DocType


def _library_path(db) -> str:
    return str(db.path.parent)


def test_acl_parent_deny_overrides_child_document_access(
    db,
    app_db,
    monkeypatch,
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    user = app_db.create_user(
        username="editor",
        display_name="Editor",
        password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role="editor",
    )
    parent = Document(name="Denied Parent", doc_type=DocType.folder)
    db.save(parent)
    child = Document(name="Child", parent_id=parent.id)
    db.save(child)
    app_db.set_library_acl_override(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        target_id=parent.id,
        effect="deny",
    )

    assert authz.can_read(user, library_path, child.id) is False
    assert authz.can_write(user, library_path, child.id) is False


def test_target_ancestor_ids_terminates_on_parent_cycle(db):
    library_path = _library_path(db)
    first = Document(name="Cycle A", doc_type=DocType.folder)
    second = Document(name="Cycle B", doc_type=DocType.folder, parent_id=first.id)
    first.parent_id = second.id
    db.save(first)
    db.save(second)

    ancestors = authz._target_ancestor_ids(library_path, first.id)

    assert ancestors == [first.id, second.id]
