"""sharing.share-on-choice / sharing.listener (#5736): the `.local` listener follows "This network".

Unset (a Mac updated from before the choice existed): on only if a device is actually paired, so an
update never drops the owner's phone; a fresh setup has none, so it stays off. An explicit choice wins.
"""

import pytest

from fichero_server import __main__ as backend_main
from fichero_server.security import accounts
from tests.unit.security.test_sharing_probe_2026_10_01 import _clear_pairing_state, harness  # noqa: F401

LAN = "192.168.1.42"


@pytest.fixture(autouse=True)
def _lan(monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: LAN)
    monkeypatch.delenv("FICHERO_THIS_NETWORK", raising=False)


def _pair_device(app_db, revoked=False):
    user = app_db.list_users()[0] if hasattr(app_db, "list_users") and app_db.list_users() else None
    user_id = user.id if user else backend_main_owner(app_db)
    device = app_db.create_device(name="iPhone", user_id=user_id, token_hash=accounts.hash_token(accounts.new_session_token()))
    if revoked:
        app_db.revoke_device(device.id)
    return device


def backend_main_owner(app_db):
    from fichero_server.api.auth import ensure_owner_account

    return ensure_owner_account(app_db).id


def test_an_update_with_a_paired_device_keeps_the_local_listener(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_LAN_HOST", "studio.local")  # sharing over .local: a pre-route device is LAN
    _pair_device(app_db)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_a_fresh_setup_with_no_device_opens_no_local_listener(app_db):
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_a_revoked_device_does_not_keep_it_open(app_db):
    _pair_device(app_db, revoked=True)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_an_explicit_off_wins_over_a_paired_device(app_db, monkeypatch):
    _pair_device(app_db)
    monkeypatch.setenv("FICHERO_THIS_NETWORK", "0")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_an_explicit_on_opens_it_with_no_device(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_THIS_NETWORK", "1")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


# The route a device paired over decides whether it keeps the .local listener open (review 75): a
# Tailscale-paired device must not, so a tailnet-only Mac stays "safe at work" after the update.


def _paired_over(app_db, route):
    device = _pair_device(app_db)
    if route is not None:
        app_db.set_device_route(device.id, route)
    return device


def test_a_tailscale_only_mac_keeps_this_network_off_after_the_update(app_db):
    _paired_over(app_db, "tailnet")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_a_device_paired_over_the_lan_keeps_it_on(app_db):
    _paired_over(app_db, "lan")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_a_mixed_mac_keeps_it_on_for_the_lan_device(app_db):
    _paired_over(app_db, "tailnet")
    _paired_over(app_db, "lan")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_a_pairing_through_tailscale_serve_is_recorded_as_tailnet(harness):
    code = harness.host().post("/api/pair/code").json()["code"]
    paired = harness.remote().post(
        "/api/pair",
        json={"code": code, "device_name": "iPhone"},
        headers={"Tailscale-User-Login": "me@example.com"},
    )
    assert paired.status_code == 200, paired.text
    assert harness.app_db.device_route(paired.json()["device_id"]) == "tailnet"


def test_a_direct_pairing_is_recorded_as_lan(harness):
    code = harness.host().post("/api/pair/code").json()["code"]
    paired = harness.remote().post("/api/pair", json={"code": code, "device_name": "iPad"})
    assert harness.app_db.device_route(paired.json()["device_id"]) == "lan"


# A device paired before the route was recorded counts as LAN only while this Mac shares over .local (review 78).


def test_a_legacy_device_counts_as_lan_when_this_mac_shares_over_dot_local(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_LAN_HOST", "studio.local")
    _paired_over(app_db, None)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_a_legacy_device_counts_as_tailscale_when_this_mac_does_not_share_over_dot_local(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_LAN_HOST", LAN)
    _paired_over(app_db, None)
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]
