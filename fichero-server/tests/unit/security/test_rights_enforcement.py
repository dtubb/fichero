"""ACCESS CONTROL: a restricting rights record refuses every account it does not name
(`source.rights.one-check`, slice 14, #4953; ruled 2026-09-20, go 2026-09-27).

Enforced inside the ONE permission check (`authz._allowed`), so every route and every audited
action inherits it. Owner and editor are not exempt: only the people a record names may see what
it restricts. What breaks without these tests: a community's restricted material shown to anyone
with a role, or -- the one that matters most -- a library with NO records behaving differently.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Document
from fichero_server.models.rights import RightsRecord
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass
from fichero_server.security import accounts, authz


@pytest.fixture
def lib(db, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    path = str(db.path.parent)
    norm = authz.normalize_library_path(path)
    users = {}
    for role in ("owner", "editor", "viewer", "unnamed"):
        user = app_db.create_user(
            username=f"rights-{role}", display_name=role, password_hash=accounts.hash_password("password"),
        )
        app_db.set_library_role(user_id=user.id, library_path=norm, role="editor" if role == "unnamed" else role)
        users[role] = user
    folder = Document(name="folder")
    db.save(folder)
    restricted = Document(name="restricted.jpg", parent_id=folder.id)
    sibling = Document(name="sibling.jpg", parent_id=folder.id)
    db.save(restricted)
    db.save(sibling)
    pass_row = SegmentPass(document_id=restricted.id, name="p", provenance_kind=ProvenanceKind.human)
    db.save(pass_row)
    boot = ActionContext(actor="system", library_path=path, is_bootstrap=True)
    made = registry.invoke(db, "segment.create", {
        "document_id": restricted.id, "pass_id": pass_row.id, "kind": "line",
        "anchor": {"document_id": restricted.id, "rect": [0.1, 0.1, 0.2, 0.05]}}, boot).result
    segment = db.get(Segment, made["segment_ids"][0])
    return path, users, folder, restricted, sibling, segment


def _restrict(db, target_kind, target_id, readers):
    record = RightsRecord(target_kind=target_kind, target_id=target_id, restricted=True, readers=readers)
    db.save(record)
    return record


def _can(users, path, target):
    return {role: (authz.can_read(u, path, target), authz.can_write(u, path, target)) for role, u in users.items()}


def test_a_library_with_no_rights_records_behaves_exactly_as_before(db, lib):
    """The maintainer's real libraries have none: roles alone decide, unchanged."""
    path, users, folder, restricted, sibling, segment = lib
    for target in (None, folder.id, restricted.id, sibling.id, segment.id):
        assert _can(users, path, target) == {
            "owner": (True, True), "editor": (True, True), "viewer": (True, False), "unnamed": (True, True),
        }, target


def test_each_role_on_a_restricted_document(db, lib):
    """Named owner and viewer keep what their role gives; the editor and the account with a role
    but no name are refused, reading and writing alike."""
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "document", restricted.id, [users["owner"].id, users["viewer"].id])
    assert _can(users, path, restricted.id) == {
        "owner": (True, True), "editor": (False, False), "viewer": (True, False), "unnamed": (False, False),
    }


def test_the_owner_is_not_exempt(db, lib):
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "document", restricted.id, [users["editor"].id])
    assert _can(users, path, restricted.id)["owner"] == (False, False)
    assert _can(users, path, restricted.id)["editor"] == (True, True)


def test_a_folder_record_passes_down_and_not_outside_the_folder(db, lib):
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "document", folder.id, [users["owner"].id])
    assert _can(users, path, segment.id)["editor"] == (False, False)
    assert _can(users, path, restricted.id)["editor"] == (False, False)
    assert _can(users, path, sibling.id)["editor"] == (False, False)  # same folder, same record
    other = Document(name="elsewhere.jpg")
    db.save(other)
    assert _can(users, path, other.id)["editor"] == (True, True)


def test_a_segment_record_restricts_that_segment_only(db, lib):
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "segment", segment.id, [users["owner"].id])
    assert _can(users, path, segment.id)["editor"] == (False, False)
    assert _can(users, path, restricted.id)["editor"] == (True, True)


def test_two_restrictions_on_the_chain_need_both_names(db, lib):
    """Tighten-only: the intersection. Named on the folder but not on the document is refused."""
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "document", folder.id, [users["owner"].id, users["editor"].id])
    _restrict(db, "document", restricted.id, [users["owner"].id])
    assert _can(users, path, restricted.id)["editor"] == (False, False)
    assert _can(users, path, sibling.id)["editor"] == (True, True)
    assert _can(users, path, restricted.id)["owner"] == (True, True)


def test_a_library_wide_restriction_reaches_everything(db, lib):
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "library", "library", [users["owner"].id])
    for target in (None, folder.id, sibling.id, segment.id):
        assert _can(users, path, target)["editor"] == (False, False), target


def test_a_withdrawn_restriction_restricts_nothing(db, lib):
    path, users, folder, restricted, sibling, segment = lib
    record = _restrict(db, "document", restricted.id, [users["owner"].id])
    ctx = ActionContext(actor=users["owner"].username, library_path=path)
    registry.invoke(db, "rights.withdraw", {"record_id": record.id}, ctx)
    assert _can(users, path, restricted.id)["editor"] == (True, True)


def test_an_unnamed_account_cannot_withdraw_the_restriction_by_its_id(db, lib):
    """The record's id resolves to the document it hangs on, so naming the record is naming the
    document: without this, the restriction could be lifted by the people it keeps out."""
    path, users, folder, restricted, sibling, segment = lib
    record = _restrict(db, "document", restricted.id, [users["owner"].id])
    ctx = ActionContext(actor=users["editor"].username, library_path=path)
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, "rights.withdraw", {"record_id": record.id}, ctx)
    assert db.get(RightsRecord, record.id).withdrawn_at is None


def test_a_restriction_that_does_not_name_its_setter_is_refused_out_loud(db, lib):
    """Never silently add the author, and never let them lock themselves out."""
    from fastapi import HTTPException

    path, users, folder, restricted, sibling, segment = lib
    ctx = ActionContext(actor=users["owner"].username, library_path=path)
    with pytest.raises(HTTPException) as refused:
        registry.invoke(db, "rights.set", {
            "target_kind": "document", "target_id": restricted.id, "restricted": True,
            "readers": [users["viewer"].id],
        }, ctx)
    assert refused.value.status_code == 422
    assert "lock you out" in refused.value.detail
    assert db.query(RightsRecord, target_id=restricted.id) == []
    made = registry.invoke(db, "rights.set", {
        "target_kind": "document", "target_id": restricted.id, "restricted": True,
        "readers": [users["owner"].id, users["viewer"].id],
    }, ctx)
    assert made.ok
    assert _can(users, path, restricted.id)["editor"] == (False, False)


def test_single_user_mode_is_untouched(db, lib, monkeypatch):
    path, users, folder, restricted, sibling, segment = lib
    _restrict(db, "document", restricted.id, [users["owner"].id])
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    assert authz.can_write(users["editor"], path, restricted.id)
