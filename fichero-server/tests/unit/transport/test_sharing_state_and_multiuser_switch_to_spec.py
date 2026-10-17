"""library-sharing: Sharing state is readable and the Multi-user switch settable through the API (#5751).

CLI/MCP are clients of the same engine route as the Settings switch. Sharing on/off itself stays
with the app supervisor (it owns the listener process); this is the state read plus the persisted
Multi-user setting.
"""

from __future__ import annotations

from tests.unit.transport.test_two_macs_end_to_end_to_spec import _bearer, two_macs  # noqa: F401


def _owner(a):
    s = a.post("/api/auth/login", json={"username": "owner", "password": "password"}).json()["session_token"]
    return _bearer(s)


def test_sharing_state_reports_multiuser_tailnet_and_device_count(two_macs, monkeypatch):  # noqa: F811
    from fichero_server.security import tailscale_serve

    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: "https://studio.tail1234.ts.net")
    owner = _owner(two_macs["a"])
    code = two_macs["a"].post("/api/pair/code", headers=owner).json()["code"]
    assert two_macs["b"].post("/api/pair", json={"code": code, "device_name": "Mac B"}).status_code == 200
    body = two_macs["a"].get("/api/pair/sharing", headers=owner).json()
    assert body["multiuser_enabled"] is True  # the fixture runs with accounts on
    assert body["tailnet_url"] == "https://studio.tail1234.ts.net"
    assert body["paired_device_count"] >= 1


def test_the_owner_sets_the_persisted_multiuser_switch(app_db, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.api.routes.auth import pairing

    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    monkeypatch.setattr(pairing, "_pairing_user", lambda *_: SimpleNamespace(is_owner=True))
    state = pairing.set_multiuser(SimpleNamespace(), pairing.MultiuserRequest(enabled=True), app_db)
    assert app_db.get_setting("multiuser.enabled") == "true"
    assert state.multiuser_enabled is True


def test_an_environment_setting_wins_and_says_so(two_macs, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    a = two_macs["a"]
    r = a.put("/api/pair/multiuser", json={"enabled": False}, headers=_owner(a))
    assert r.status_code == 409
