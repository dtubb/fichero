"""`sharing.stale-forward-says-so` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.3).

A tailnet port held by a forward Fichero did not make is reported with the one command that frees it, and the generic
`tailscale serve --bg ...` line (which fails the same way) is withheld while the conflict stands.
"""
from __future__ import annotations

from fichero_server.security import tailscale_serve as ts
from tests.unit.security.test_tailscale_serve import cli  # noqa: F401  -- the fake `tailscale serve`
from tests.unit.transport.test_sharing_state_and_multiuser_switch_to_spec import _owner
from tests.unit.transport.test_two_macs_end_to_end_to_spec import two_macs  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def test_a_raw_forward_to_another_service_is_reported_with_the_command_that_frees_it(cli, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}
    assert ts.forward_conflict(8765) == {"holds": "tcp://localhost:8000", "free_with": "tailscale serve --tcp=8765 off"}


def test_an_https_forward_to_another_service_is_freed_with_the_https_command(cli, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    cli.status["TCP"]["8765"] = {"HTTPS": True}
    cli.status["Web"] = {"m.tail.ts.net:8765": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8000"}}}}
    assert ts.forward_conflict(8765)["free_with"] == "tailscale serve --https=8765 off"


def test_our_own_forward_a_free_port_and_the_old_raw_forward_are_no_conflict(cli, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    assert ts.forward_conflict(8765) is None  # free
    cli.status["TCP"]["8765"] = {"TCPForward": "127.0.0.1:8765"}
    assert ts.forward_conflict(8765) is None  # the earlier engines' raw forward is replaced, not a conflict
    ts.ensure_forward(8765, "tailscale")
    assert ts.forward_conflict(8765) is None  # ours


def test_an_engine_that_is_not_sharing_asks_tailscale_nothing(cli, monkeypatch):
    for name in ("FICHERO_TCP_TLS_ALSO", "FICHERO_LAN_HOST", "FICHERO_PUBLIC_BASE_URL", "FICHERO_TAILNET_URL"):
        monkeypatch.delenv(name, raising=False)
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}
    assert ts.forward_conflict(8765) is None


def test_sharing_state_carries_the_conflict_and_withholds_the_generic_command(two_macs, cli, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}
    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["tailnet_serve_conflict"] == {"holds": "tcp://localhost:8000", "free_with": "tailscale serve --tcp=8765 off"}
    assert body["tailnet_serve_command"] is None


def test_sharing_state_has_no_conflict_when_the_port_is_free(two_macs, cli, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://m.tail.ts.net")
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["tailnet_serve_conflict"] is None
    assert body["tailnet_serve_command"]  # the generic command is still offered when nothing blocks it
