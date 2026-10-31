"""`sharing.tailnet-forward-whenever-tailscale-is-up` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.1).

The one address that worked from every Mac on the campus network (2026-10-30) was the tailnet name, but the engine
made its `tailscale serve` forward only when the SHARING address itself was a `.ts.net` name. A `.local` sharer with
Tailscale running gets the forward too, so the share sheet's Tailscale row works whichever address the person chose.
A foreign forward is still never replaced.
"""
from __future__ import annotations

import logging

from fichero_server.security import tailscale_serve as ts
from tests.unit.security.test_tailscale_serve import WANT, cli  # noqa: F401  # the fake `tailscale serve`

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose

LOG = logging.getLogger("test")
LOCAL_SHARER = {"FICHERO_PUBLIC_BASE_URL": "https://macbook-air-m1.local:8765", "FICHERO_TLS_CERTFILE": "/c.pem"}


def test_a_local_sharer_with_tailscale_running_gets_the_forward(cli, monkeypatch) -> None:
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    assert ts.start_for_engine(LOCAL_SHARER, log=LOG) == ("tailscale", 8765)
    assert ts.forward_target(cli.status, 8765) == WANT


def test_a_local_sharer_without_tailscale_running_forwards_nothing(cli, monkeypatch) -> None:
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "")
    assert ts.start_for_engine(LOCAL_SHARER, log=LOG) is None
    assert ts.forward_target(cli.status, 8765) is None


def test_a_foreign_forward_is_still_not_replaced_for_a_local_sharer(cli, monkeypatch) -> None:
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}  # the M4's stale raw forward, seen 2026-10-30
    assert ts.start_for_engine(LOCAL_SHARER, log=LOG) is None
    assert ts.forward_target(cli.status, 8765) == "tcp://localhost:8000"


def test_the_forward_state_is_named(cli, monkeypatch) -> None:
    """`ours` / `foreign` / `none`: what `GET /api/pair/sharing` reports as `tailnet_forward`."""
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    monkeypatch.setattr(ts.os, "environ", dict(LOCAL_SHARER))  # forward_state reads the engine's own sharing state
    assert ts.forward_state(8765) == "none"
    ts.start_for_engine(LOCAL_SHARER, log=LOG)
    assert ts.forward_state(8765) == "ours"
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}
    cli.status.get("Web", {}).pop("m.tail.ts.net:8765", None)
    assert ts.forward_state(8765) == "foreign"
    monkeypatch.setattr(ts, "tailscale_cli", lambda: None)
    assert ts.forward_state(8765) == "none"


# -- review 2026-10-31 (H): a forward is made only for an engine that is SHARING -----------------------------------------
NOT_SHARING_CERT_ONLY = {"FICHERO_TLS_CERTFILE": "/c.pem"}  # start_fichero_server.sh: a loopback certificate, no sharing address
APP_NOT_HOSTING = {"FICHERO_TLS_CERTFILE": "/c.pem", "FICHERO_UDS_PATH": "/tmp/x.sock"}  # the app with Sharing off
LOOPBACK_ONLY = {"FICHERO_TLS_CERTFILE": "/c.pem", "FICHERO_PUBLIC_BASE_URL": "https://127.0.0.1:8765"}


def test_a_non_sharing_engine_with_a_certificate_and_tailscale_up_makes_no_forward(cli, monkeypatch) -> None:
    """A dev or headless engine that nobody shared must never be published on the tailnet, and must not even ask
    Tailscale: no `serve`, no `status`."""
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    for env in (NOT_SHARING_CERT_ONLY, APP_NOT_HOSTING, LOOPBACK_ONLY):
        cli.calls.clear()
        assert ts.start_for_engine(env, log=LOG) is None, env
        assert cli.calls == [], f"a non-sharing engine touched tailscale: {cli.calls}"
    assert ts.forward_target(cli.status, 8765) is None


def test_the_app_hosting_on_the_lan_is_sharing(cli, monkeypatch) -> None:
    """The app sets FICHERO_TCP_TLS_ALSO=1 and FICHERO_LAN_HOST only while hosting: that is the sharing signal."""
    monkeypatch.setattr(ts, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    hosting = {**APP_NOT_HOSTING, "FICHERO_TCP_TLS_ALSO": "1", "FICHERO_LAN_HOST": "192.0.2.10",
               "FICHERO_PUBLIC_BASE_URL": "https://macbook-air-m1.local:8765"}
    assert ts.start_for_engine(hosting, log=LOG) == ("tailscale", 8765)


def test_sharing_on_is_one_predicate() -> None:
    assert not ts.sharing_on(NOT_SHARING_CERT_ONLY)
    assert not ts.sharing_on(APP_NOT_HOSTING)
    assert not ts.sharing_on(LOOPBACK_ONLY)
    assert ts.sharing_on({"FICHERO_PUBLIC_BASE_URL": "https://macbook-air-m1.local:8765"})
    assert ts.sharing_on({"FICHERO_TCP_TLS_ALSO": "1"})
    assert ts.sharing_on({"FICHERO_LAN_HOST": "192.0.2.10"})
    assert ts.sharing_on({"FICHERO_TAILNET_URL": "https://m.tail.ts.net"})


def test_forward_state_asks_tailscale_nothing_while_not_sharing(cli, monkeypatch) -> None:
    """`GET /api/pair/sharing` with Sharing off: "none" without a subprocess (review M: no `serve status` per read)."""
    monkeypatch.setattr(ts.os, "environ", dict(APP_NOT_HOSTING))
    assert ts.forward_state(8765) == "none"
    assert cli.calls == []


# -- review 2026-10-31 (H4): "unknown" (the engine cannot ask Tailscale: a sandboxed build) is not "none" (free) --------------
def test_forward_state_says_unknown_when_the_cli_cannot_be_run(monkeypatch) -> None:
    import subprocess

    monkeypatch.setattr(ts.os, "environ", dict(LOCAL_SHARER))
    monkeypatch.setattr(ts, "tailscale_cli", lambda: "/Applications/Tailscale.app/Contents/MacOS/Tailscale")
    for failure in (PermissionError("Operation not permitted"), subprocess.TimeoutExpired("tailscale", 20),
                    subprocess.CalledProcessError(1, "tailscale"), ValueError("no JSON")):
        def refuse(args, _f=failure):
            raise _f
        monkeypatch.setattr(ts, "_run", refuse)
        assert ts.forward_state(8765) == "unknown", failure


def test_forward_state_says_none_when_tailscale_is_not_installed_or_the_port_is_free(cli, monkeypatch) -> None:
    monkeypatch.setattr(ts.os, "environ", dict(LOCAL_SHARER))
    assert ts.forward_state(8765) == "none"  # installed, port free
    monkeypatch.setattr(ts, "tailscale_cli", lambda: None)
    assert ts.forward_state(8765) == "none"  # not installed: a known state, not an unknown one
