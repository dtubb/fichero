"""sharing.marks.host-row (#5738): the paired-device list names the person each device is signed in as, beside the id.

The host's Inspector reads "<person> on <device>"; it cannot, from `user_id` alone.
"""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _multiuser_on,
    _pair_as,
    harness,
)


def test_the_device_list_carries_each_devices_person_by_name(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    alice = _pair_as(harness, "alice", "Alice's Mac")
    bob = _pair_as(harness, "bob", "Bob's iPad")
    items = {d["id"]: d for d in harness.host().get("/api/pair/devices").json()["items"]}
    assert items[alice["device_id"]]["username"] == "alice"
    assert items[bob["device_id"]]["username"] == "bob"
    assert items[alice["device_id"]]["user_id"] != items[bob["device_id"]]["user_id"]
