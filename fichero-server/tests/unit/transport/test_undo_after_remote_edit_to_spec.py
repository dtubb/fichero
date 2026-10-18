"""sharing.undo-after-remote-edit (#5733): the host's undo never reaches over a paired Mac's later edit.

The owner edits a note on the host, a second person edits the same note from a paired Mac,
and the owner's take-back is refused 409 `changed` in a sentence naming that person.
"""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)


def test_the_hosts_undo_is_refused_after_a_paired_person_edits_the_same_note(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "alice", "Alice's Mac")
    host, remote, alice = harness.host(), harness.remote(), _bearer(dev["device_token"])
    note_id = host.post("/api/notes", json={"body": "draft"}).json()["id"]
    before = {a.id for a in harness.audit_rows()}
    assert host.patch(f"/api/notes/{note_id}", json={"body": "host words"}).status_code == 200
    mine = next(a for a in harness.audit_rows() if a.id not in before)
    assert remote.patch(f"/api/notes/{note_id}", json={"body": "alice words"}, headers=alice).status_code == 200

    refused = host.post("/api/actions/audit/undo", json={"audit_ids": [mine.id]})

    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["reason"] == "changed" and "alice" in body["detail"]
    assert host.get(f"/api/notes/{note_id}").json()["body"] == "alice words"
