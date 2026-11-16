"""sharing.marks.host-row (#5738): the paired-device list names the person each device is signed in as, beside the id.

The host's Inspector reads "<person> on <device>"; it cannot, from `user_id` alone.
"""

from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _multiuser_on,
    _pair_as,
    harness,
)


def test_the_device_list_carries_each_devices_person_by_name(harness, monkeypatch):  # noqa: F811
    users = _multiuser_on(harness, monkeypatch)
    alice = _pair_as(harness, "alice", "Alice's Mac")
    bob = _pair_as(harness, "bob", "Bob's iPad")
    owner = signed_in_client(harness, users["owner"])
    items = {d["id"]: d for d in harness.client().get("/api/pair/devices", headers=owner.headers).json()["items"]}
    assert items[alice["device_id"]]["username"] == "alice"
    assert items[bob["device_id"]]["username"] == "bob"
    assert items[alice["device_id"]]["user_id"] != items[bob["device_id"]]["user_id"]
