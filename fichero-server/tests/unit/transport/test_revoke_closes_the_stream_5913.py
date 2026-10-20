"""sharing.revoke-closes-the-stream (#5913): revoking a paired device ends the change streams that device holds, at once.

Spec: docs/contributor_manual/specs/transport/library-sharing.md. The stream checked its caller only at connect, so a revoked
guest kept receiving changes until it hung up. Revoking the device (and every device it paired) puts a last
`sharing.revoked` frame on that device's subscriptions and nobody else's.
"""
from __future__ import annotations

from fichero_server.api.change_stream import ChangeEvent, _change_hub
from fichero_server.security import accounts

LIB = "/tmp/revoke-closes-the-stream.fichero"


def _device(app_db, name, parent=None):
    owner = next(iter(app_db.list_users()), None) or app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True)
    device = app_db.create_device(name=name, user_id=owner.id, token_hash=accounts.hash_token(accounts.new_session_token()))
    if parent is not None:
        app_db.conn.execute("UPDATE devices SET paired_by_device_id = ? WHERE id = ?", [parent.id, device.id])
        app_db.conn.commit()
    return device


def _drain(queue):
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait().type)
    return seen


def _watch(device_id):
    subscription = _change_hub.connect(LIB, device_id=device_id)
    return subscription.queue


def test_revoking_a_device_ends_its_stream_with_a_last_frame_and_nobody_elses(app_db):
    guest, other = _device(app_db, "guest"), _device(app_db, "other")
    guest_stream, other_stream, host_stream = _watch(guest.id), _watch(other.id), _watch(None)
    try:
        app_db.revoke_device(guest.id)
        assert _drain(guest_stream) == ["sharing.revoked"]
        assert _drain(other_stream) == [] and _drain(host_stream) == []
        _change_hub.emit(LIB, ChangeEvent(type="document.updated"))
        assert _drain(other_stream) == ["document.updated"], "an untouched stream still gets changes"
    finally:
        for q in (guest_stream, other_stream, host_stream):
            _change_hub.unsubscribe(LIB, q)


def test_revoking_a_device_also_ends_the_streams_of_the_devices_it_paired(app_db):
    parent = _device(app_db, "parent")
    child = _device(app_db, "child", parent=parent)
    child_stream = _watch(child.id)
    try:
        app_db.revoke_device(parent.id)
        assert _drain(child_stream) == ["sharing.revoked"]
    finally:
        _change_hub.unsubscribe(LIB, child_stream)
