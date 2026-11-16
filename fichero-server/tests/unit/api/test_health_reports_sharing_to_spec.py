"""`sharing.health-reports-sharing` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.4).

`GET /api/health` carries a `sharing` block next to `remote_backend`, so a tester and the Add Device sheet read what the
engine is listening on instead of guessing from `remote_backend.enabled=false`. No secret is in it.
`GET /api/pair/sharing` gains `multiuser_blocker`: why accounts cannot be turned on yet, else none.
"""
from __future__ import annotations

from tests.unit.transport.test_sharing_state_and_multiuser_switch_to_spec import _owner
from tests.unit.transport.test_two_macs_end_to_end_to_spec import two_macs  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def _quiet_network(monkeypatch, *, tailnet="", forward="none", lan="192.0.2.10"):
    from fichero_server.security import bind_host, sharing_report, tailscale_serve

    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: tailnet)
    monkeypatch.setattr(tailscale_serve, "forward_state", lambda port: forward)
    monkeypatch.setattr(bind_host, "primary_lan_ip", lambda: lan)
    sharing_report._cache.clear()  # the tailnet answer is kept for seconds; a test starts clean


def _health(two_macs):
    # No project named: the engine's own answer, which is what a tester or the Add Device sheet reads.
    return two_macs["a"].get("/api/health", headers={"X-Fichero-Library-Path": ""})


def test_health_says_sharing_is_off_when_the_engine_listens_on_loopback_only(two_macs, monkeypatch):
    for name in ("FICHERO_TCP_TLS_ALSO", "FICHERO_LAN_HOST", "FICHERO_PUBLIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    _quiet_network(monkeypatch)
    block = _health(two_macs).json()["sharing"]
    assert block["on"] is False
    assert block["listeners"] == ["127.0.0.1:8765"]
    assert block["tailnet_forward"] == "none"
    assert block["paired_devices"] == 0


def test_health_names_the_listeners_the_addresses_and_who_holds_the_forward(two_macs, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_LAN_HOST", "192.0.2.10")
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://macbook-air-m1.local:8765")
    _quiet_network(monkeypatch, tailnet="https://m.tail.ts.net", forward="ours")
    block = _health(two_macs).json()["sharing"]
    assert block["on"] is True
    assert block["listeners"] == ["127.0.0.1:8765", "192.0.2.10:8765"]
    assert block["tailnet_forward"] == "ours"
    assert block["multiuser"] is True  # the fixture runs with accounts on
    rows = {(a["kind"], a["url"]): a["listening"] for a in block["addresses"]}
    assert rows[("tailnet", "https://m.tail.ts.net")] is True  # Fichero's own forward reaches the loopback listener
    assert rows[("local-name", "https://macbook-air-m1.local:8765")] is True
    assert rows[("lan", "https://192.0.2.10:8765")] is True


def test_health_does_not_call_a_foreign_forward_listening(two_macs, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.delenv("FICHERO_LAN_HOST", raising=False)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    _quiet_network(monkeypatch, tailnet="https://m.tail.ts.net", forward="foreign")
    block = _health(two_macs).json()["sharing"]
    assert block["tailnet_forward"] == "foreign"
    assert [a["listening"] for a in block["addresses"] if a["kind"] == "tailnet"] == [False]


def test_health_carries_no_secret(two_macs, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    _quiet_network(monkeypatch)
    text = str(_health(two_macs).json()["sharing"])
    assert "token" not in text.lower() and "password" not in text.lower() and "spki" not in text.lower()


def test_sharing_state_says_why_accounts_cannot_be_turned_on(two_macs, monkeypatch):
    from fichero_server.security import multiuser

    _quiet_network(monkeypatch)
    monkeypatch.setattr(multiuser, "owner_password_gap", lambda app_db: "choose an owner password first")
    monkeypatch.setattr(multiuser, "multiuser_enabled", lambda: False)
    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["multiuser_blocker"] == "choose an owner password first"


def test_sharing_state_has_no_blocker_when_accounts_are_on(two_macs, monkeypatch):
    _quiet_network(monkeypatch)
    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["multiuser_enabled"] is True and body["multiuser_blocker"] is None
