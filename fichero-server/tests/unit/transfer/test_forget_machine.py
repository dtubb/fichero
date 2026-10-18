"""transfer.machine.forget-machine (#5661): forgetting a paired machine drops its saved token on this Mac.

It does not revoke the device on the far Mac (that is the far Mac's Sharing list).
"""

from __future__ import annotations

from tests.unit.transfer._two_projects import open_source
from tests.unit.transfer.test_transfer_between_machines import _pair, _send, far  # noqa: F401


def test_forgetting_a_machine_removes_it_and_a_send_is_then_refused(client, db, tmp_path, far):  # noqa: F811
    machine_id = _pair(client)

    forgotten = client.delete(f"/api/machines/{machine_id}")
    assert forgotten.status_code == 200, forgotten.text
    assert client.get("/api/machines").json() == []
    sent = _send(client, open_source(tmp_path), db, machine_id)
    assert sent.status_code == 404, sent.text
    assert far.puts == 0


def test_forgetting_an_unknown_machine_is_404(client, far):  # noqa: F811
    assert client.delete("/api/machines/" + "0" * 32).status_code == 404
