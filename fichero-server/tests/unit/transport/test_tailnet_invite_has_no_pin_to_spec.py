"""library-sharing: system trust for .ts.net, an SPKI pin only for .local (#5753; ruling).

A .ts.net invite carries no pin, and pairing over a .ts.net host does not need one configured:
Tailscale's certificate is publicly trusted, the engine's own key is not what the guest sees.
A .local (or any other) host still needs and carries the pin.
"""

from __future__ import annotations

from tests.unit.transport.test_two_macs_end_to_end_to_spec import _bearer, two_macs  # noqa: F401


def _mint(a):
    session = a.post("/api/auth/login", json={"username": "owner", "password": "password"}).json()["session_token"]
    return a.post("/api/pair/code", headers=_bearer(session))


def test_a_ts_net_invite_carries_no_pin(two_macs, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://studio.tail1234.ts.net:8765")
    body = _mint(two_macs["a"]).json()
    assert body["tailnet_url"] == "https://studio.tail1234.ts.net:8765"
    assert body["spki_pin"] is None


def test_pairing_over_a_ts_net_host_needs_no_configured_pin(two_macs, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://studio.tail1234.ts.net:8765")
    code = _mint(two_macs["a"]).json()["code"]
    monkeypatch.delenv("FICHERO_TLS_SPKI_HASH", raising=False)
    b = two_macs["tailnet_b"]
    assert b.post("/api/pair", json={"code": code, "device_name": "Mac B"}).status_code == 200


def test_a_local_invite_still_carries_the_pin(two_macs, monkeypatch):  # noqa: F811
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://studio.local:8765")
    assert _mint(two_macs["a"]).json()["spki_pin"] == "c3BraS1waW4="


def test_the_detected_tailnet_address_is_offered_to_the_owner(two_macs, monkeypatch):  # noqa: F811
    from fichero_server.security import tailscale_serve

    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: "https://studio.tail1234.ts.net")
    session = two_macs["a"].post("/api/auth/login", json={"username": "owner", "password": "password"}).json()["session_token"]
    r = two_macs["a"].get("/api/pair/tailnet", headers=_bearer(session))
    assert r.status_code == 200
    assert r.json() == {"tailnet_url": "https://studio.tail1234.ts.net"}


def test_no_tailscale_means_an_empty_offer(two_macs, monkeypatch):  # noqa: F811
    from fichero_server.security import tailscale_serve

    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: "")
    session = two_macs["a"].post("/api/auth/login", json={"username": "owner", "password": "password"}).json()["session_token"]
    assert two_macs["a"].get("/api/pair/tailnet", headers=_bearer(session)).json() == {"tailnet_url": None}


def test_a_local_invite_keeps_its_pin_even_when_tailscale_is_up(two_macs, monkeypatch):  # noqa: F811
    # Tailscale up (an explicit tailnet URL) must not drop the pin from a .local sharing address.
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://studio.local:8765")
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://studio.tail1234.ts.net")
    body = _mint(two_macs["a"]).json()
    assert body["spki_pin"] == "c3BraS1waW4="
    assert body["tailnet_url"] == "https://studio.tail1234.ts.net"


def test_a_forged_ts_net_host_header_does_not_skip_the_pin(two_macs, monkeypatch):  # noqa: F811
    # The skip comes from what this engine shares at, never from the caller's Host header.
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://studio.local:8765")
    code = _mint(two_macs["a"]).json()["code"]
    monkeypatch.delenv("FICHERO_TLS_SPKI_HASH", raising=False)
    r = two_macs["tailnet_b"].post("/api/pair", json={"code": code, "device_name": "Mac B"})
    assert r.status_code != 200
