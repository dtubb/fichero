"""sharing.names-on-edits (#5735): two accounts, one library, every edit names its author.

The owner edits on the host Mac (loopback, no device); a second person signed in on a
paired Mac edits over the network. Reuses the two-machine harness of the sharing probe.
"""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)


def test_two_accounts_each_edit_names_its_person_and_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "alice", "Alice's Mac")
    host, remote, alice = harness.host(), harness.remote(), _bearer(dev["device_token"])
    before = {a.id for a in harness.audit_rows()}

    mine = host.post("/api/notes", json={"body": "from the host"})
    theirs = remote.post("/api/notes", json={"body": "from B"}, headers=alice)
    assert mine.status_code == 200 and theirs.status_code == 200

    rows = {a.target_ids[0] if a.target_ids else a.id: a for a in harness.audit_rows() if a.id not in before}
    by_actor = {a.actor: a for a in rows.values()}
    assert set(by_actor) == {"owner", "alice"}
    assert by_actor["owner"].device is None
    assert by_actor["alice"].device == {"id": dev["device_id"], "name": "Alice's Mac"}
    # both edits are in the one library, readable from the other Mac
    assert remote.get(f"/api/notes/{mine.json()['id']}", headers=alice).status_code == 200
    assert host.get(f"/api/notes/{theirs.json()['id']}").status_code == 200
