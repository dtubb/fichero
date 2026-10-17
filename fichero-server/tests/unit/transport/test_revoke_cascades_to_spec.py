"""sharing.revoke-cascades (#5351): revoking a paired device revokes every device it paired, down the chain.

Multi-user on: a person signed in on a paired Mac can mint a code, so a chain of devices exists.
"""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)


def _pair_via(harness, parent):
    """A new device paired with a code the `parent` device minted."""
    return harness.pair(harness.remote(), device_name="child", code_headers=_bearer(parent["device_token"]))


def test_revoking_a_device_revokes_the_devices_it_paired_down_the_chain(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    parent = _pair_as(harness, "alice", "Alice's Mac")
    child = _pair_via(harness, parent)
    grandchild = _pair_via(harness, child)
    sibling = _pair_as(harness, "alice", "Alice's iPad")  # paired by the host, not by parent

    assert harness.host().post(f"/api/pair/devices/{parent['device_id']}/revoke").status_code == 200

    revoked = {d.id: d.revoked for d in harness.app_db.list_devices()}
    assert revoked[parent["device_id"]] and revoked[child["device_id"]] and revoked[grandchild["device_id"]]
    assert not revoked[sibling["device_id"]]
    assert harness.remote().get("/api/pair/devices", headers=_bearer(grandchild["device_token"])).status_code == 401


def test_the_device_list_says_who_paired_each_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    parent = _pair_as(harness, "alice", "Alice's Mac")
    child = _pair_via(harness, parent)
    items = {d["id"]: d for d in harness.host().get("/api/pair/devices").json()["items"]}
    assert items[child["device_id"]]["paired_by_device_id"] == parent["device_id"]
    assert items[parent["device_id"]]["paired_by_device_id"] is None
