"""sharing.names-on-edits (#5735): the change event names the person and the device, not only a category.

Second person on a paired Mac edits; the event the host's windows receive says who and from which device.
The host's own edit names the owner and no device.
"""

from fichero_server.api import change_stream
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    _pair_as,
    harness,
)


def _capture(monkeypatch):
    seen = []
    real = change_stream._change_hub.emit
    monkeypatch.setattr(change_stream._change_hub, "emit", lambda lib, ev: (seen.append(ev), real(lib, ev))[1])
    return seen


def test_the_event_names_the_person_and_device_who_edited(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "alice", "Alice's Mac")
    host, remote, alice = harness.host(), harness.remote(), _bearer(dev["device_token"])
    seen = _capture(monkeypatch)

    assert host.post("/api/notes", json={"body": "from the host"}).status_code == 200
    assert remote.post("/api/notes", json={"body": "from B"}, headers=alice).status_code == 200

    notes = [e for e in seen if e.type.startswith("note") or e.type.startswith("research")]
    assert len(notes) == 2, [e.type for e in seen]
    mine, theirs = notes
    assert (mine.person, mine.device) == ("owner", None)
    assert (theirs.person, theirs.device) == ("alice", "Alice's Mac")
