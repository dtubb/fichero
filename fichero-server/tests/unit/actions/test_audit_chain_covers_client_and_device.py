"""review 85 + 93: a row marked v2 hashes the client and the paired device; a row written before still verifies."""
from __future__ import annotations

from fichero_server.actions.audit_chain import (
    V2_PREFIX, _HASH_FIELDS, action_audit_hash_payload, compute_action_audit_hash, save_chained_audit, verify_audit_chain,
)
from fichero_server.models import ActionAudit


def _row(**kw) -> ActionAudit:
    return ActionAudit(id="a1", action_name="user.create", actor="bootstrap", **kw)


def test_rewriting_the_device_or_client_of_a_v2_row_changes_its_hash():
    base = _row(device={"id": "d1", "name": "Mac"}, client="fichero-cli")
    h = compute_action_audit_hash(base, v2=True)
    assert h.startswith(V2_PREFIX)
    for edit in ({"device": {"id": "d2", "name": "Mac"}}, {"client": "fichero-mcp"}):
        assert compute_action_audit_hash(base.model_copy(update=edit), v2=True) != h


def test_an_old_style_payload_ignores_client_and_device():
    assert set(action_audit_hash_payload(_row(client="fichero-cli"))) == set(_HASH_FIELDS)
    row = _row(client="fichero-cli", device={"id": "d1"})
    assert compute_action_audit_hash(row) == compute_action_audit_hash(row.model_copy(update={"client": "x"}))


def test_an_old_style_row_with_a_client_still_verifies_and_a_v2_row_edit_does_not(db):
    old = _row(client="fichero-mcp", device={"id": "d1", "name": "Mac"}, chain_seq=1)
    old.row_hash = compute_action_audit_hash(old)  # written before client and device were hashed
    db.save(old)
    new = ActionAudit(id="a2", action_name="x.y", actor="ui", client="fichero-cli", device={"id": "d9", "name": "Pad"})
    save_chained_audit(db, new)

    assert verify_audit_chain(db).ok

    stored = db.get(ActionAudit, "a2")
    stored.device = {"id": "forged", "name": "Pad"}
    db.save(stored)
    assert not verify_audit_chain(db).ok
