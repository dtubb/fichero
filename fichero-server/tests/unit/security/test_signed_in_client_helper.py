"""The `signed_in_client` test helper (slice 3) gives a real session through the real routes."""

from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401


def test_signed_in_client_is_a_real_session_for_that_person_and_client(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    who = signed_in_client(harness, users["bob"], kind="cli", name="fichero CLI")
    identity = harness.client().get("/api/auth/identity", headers=who.headers).json()
    assert identity["user"]["username"] == "bob"
    assert identity["client"] == {"id": who.client.id, "kind": "cli", "name": "fichero CLI"}
