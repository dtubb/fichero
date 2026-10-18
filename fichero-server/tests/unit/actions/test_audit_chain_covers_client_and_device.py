"""review 85: the audit hash covers the client and the paired device when a row has them (legacy rows hash as before)."""
from __future__ import annotations

from fichero_server.actions.audit_chain import _HASH_FIELDS, action_audit_hash_payload, compute_action_audit_hash
from fichero_server.models import ActionAudit


def _row(**kw) -> ActionAudit:
    return ActionAudit(id="a1", action_name="user.create", actor="bootstrap", **kw)


def test_rewriting_the_device_or_client_changes_the_hash():
    base = _row(device={"id": "d1", "name": "Mac"}, client="fichero-cli")
    h = compute_action_audit_hash(base)
    assert compute_action_audit_hash(_row(device={"id": "d2", "name": "Mac"}, client="fichero-cli").model_copy(
        update={"created_at": base.created_at})) != h
    assert compute_action_audit_hash(_row(device={"id": "d1", "name": "Mac"}, client="fichero-mcp").model_copy(
        update={"created_at": base.created_at})) != h


def test_a_row_without_client_or_device_hashes_exactly_as_before():
    assert set(action_audit_hash_payload(_row())) == set(_HASH_FIELDS)
