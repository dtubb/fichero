"""Connected-clients presence (Sharing pane, 2026-08-27)."""

from __future__ import annotations

from fichero_server.api import client_presence


def _reset():
    with client_presence._LOCK:
        client_presence._SEEN.clear()


def test_named_clients_and_uds_app_traffic_are_recorded():
    _reset()
    client_presence.record("fichero-cli", transport=None)
    client_presence.record("fichero-cli", transport=None)
    client_presence.record("fichero-mcp", transport="uds")
    client_presence.record(None, transport="uds")   # the app itself
    client_presence.record(None, transport=None)    # anonymous TCP: ignored

    snap = {row["client"]: row for row in client_presence.snapshot()}
    assert snap["fichero-cli"]["requests"] == 2
    assert snap["fichero-mcp"]["transport"] == "uds"
    assert snap[client_presence.APP_CLIENT_NAME]["requests"] == 1
    assert len(snap) == 3


def test_clients_endpoint_serves_the_snapshot():
    import asyncio

    _reset()
    client_presence.record("fichero-cli", transport=None)
    from fichero_server.api.main import connected_clients

    payload = asyncio.get_event_loop().run_until_complete(connected_clients())
    assert [c.client for c in payload.clients] == ["fichero-cli"]
