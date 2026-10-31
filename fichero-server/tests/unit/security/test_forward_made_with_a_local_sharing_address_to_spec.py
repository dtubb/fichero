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
    assert ts.forward_state(8765) == "none"
    ts.start_for_engine(LOCAL_SHARER, log=LOG)
    assert ts.forward_state(8765) == "ours"
    cli.status["TCP"]["8765"] = {"TCPForward": "localhost:8000"}
    cli.status.get("Web", {}).pop("m.tail.ts.net:8765", None)
    assert ts.forward_state(8765) == "foreign"
    monkeypatch.setattr(ts, "tailscale_cli", lambda: None)
    assert ts.forward_state(8765) == "none"
