"""Sharing release bar (#5910) driven by two real engines (#5911, spec `testenv.two-engines`).

Item 8: the host survives Sharing and Multi-user switched on and off in a loop. Item 1: a guest pairs to the host over the host's LAN listener, with the pin checked against the certificate the host
presents, and the device token it gets then works on the host over that listener. M4 only (`FICHERO_TWO_ENGINES=1`).
"""
from __future__ import annotations

import httpx
import pytest

from tests.integration import _two_engines as engines

pytestmark = [engines.requires_two_engines, pytest.mark.load_sensitive]


@pytest.fixture(scope="module")
def pair():
    lan = engines.lan_address()
    if lan is None:
        pytest.skip("this Mac has no LAN address")
    # Multi-user on (owner signed in, password chosen, switch on, engine restarted): the state in which the owner signs in as a person to mint a code.
    host = engines.start_host(lan, multiuser=True)
    try:
        guest = engines.start_guest()
    except Exception:
        host.stop()
        raise
    yield host, guest
    guest.stop()
    host.stop()


def test_the_harness_never_uses_the_owners_port(pair):
    host, guest = pair
    assert host.port not in (None, engines.SHIPPED_PORT) and guest.port is None


def test_the_host_really_listens_on_the_lan_address(pair):
    host, _guest = pair
    with httpx.Client(verify=host.lan_ssl(), base_url=f"https://{host.lan}:{host.port}", timeout=15) as client:
        assert client.get("/api/health").status_code == 200


def test_release_bar_1_a_guest_pairs_over_the_lan_listener(pair):
    host, guest = pair
    with host.uds as local:
        minted = local.post("/api/pair/code")
        assert minted.status_code == 200, minted.text  # the host minted a link only because it listens where it names
        link = engines.pairing_link(host, minted.json()["code"])

    paired = engines.pair_with_link(guest, link)
    assert paired["device_token"] and paired["device_id"]

    with httpx.Client(verify=host.lan_ssl(), base_url=f"https://{host.lan}:{host.port}", timeout=15) as client:
        ok = client.get("/api/actions/registry", headers={"Authorization": f"Bearer {paired['device_token']}"})
        assert ok.status_code == 200, ok.text
        assert client.get("/api/actions/registry").status_code == 401, "auth still enforced on the LAN listener"


def test_a_wrong_pin_is_refused_and_nothing_is_redeemed(pair):
    host, guest = pair
    with host.uds as local:
        code = local.post("/api/pair/code").json()["code"]
    link = engines.pairing_link(host, code, pin="AAAA")
    with pytest.raises(RuntimeError, match="pin"):
        engines.pair_with_link(guest, link)


def _paired_guest_device(host, guest):
    with host.uds as local:
        code = local.post("/api/pair/code").json()["code"]
    return engines.pair_with_link(guest, engines.pairing_link(host, code))


def _lan_stream(host, device_token):
    headers = {"Authorization": f"Bearer {device_token}", **(host.library or {})}
    return engines.Stream(f"https://{host.lan}:{host.port}/api/activity/stream", headers, host.lan_ssl())


def test_release_bar_3_http_half_a_rename_by_either_side_is_seen_by_the_other(pair):
    """`sharing.edits-both-ways` (#5049), HTTP half: the paired device renames a note on the host over the LAN listener and the
    host sees it; the host renames it and the device sees that. The CLI-level read is r1's, in fichero-cli/tests."""
    host, guest = pair
    host.make_library("Both ways")
    paired = _paired_guest_device(host, guest)
    device = {"Authorization": f"Bearer {paired['device_token']}", **host.library}
    with host.uds as local, httpx.Client(verify=host.lan_ssl(), base_url=f"https://{host.lan}:{host.port}", timeout=30) as lan:
        note = local.post("/api/notes", json={"title": "first", "body": "x"}, headers=host.library).json()
        renamed = lan.patch(f"/api/notes/{note['id']}", json={"title": "renamed by the guest"}, headers=device)
        assert renamed.status_code == 200, renamed.text
        assert local.get(f"/api/notes/{note['id']}", headers=host.library).json()["title"] == "renamed by the guest"
        local.patch(f"/api/notes/{note['id']}", json={"title": "renamed by the host"}, headers=host.library).raise_for_status()
        assert lan.get(f"/api/notes/{note['id']}", headers=device).json()["title"] == "renamed by the host"


def test_release_bar_4_remove_refuses_the_device_at_once_and_closes_its_stream(pair):
    """`sharing.revoke`, `sharing.revoke-closes-the-stream` (#5351, #5913): the owner removes the paired device; its open
    stream ends and its token is refused on the LAN listener on the very next request."""
    host, guest = pair
    host.make_library("Revoke bar")
    paired = _paired_guest_device(host, guest)
    stream = _lan_stream(host, paired["device_token"])
    stream.wait_open()
    with host.uds as local:
        removed = local.post(f"/api/pair/devices/{paired['device_id']}/revoke")
        assert removed.status_code == 200, removed.text
    assert stream.ended.wait(15), "the removed device's stream is still open"
    with httpx.Client(verify=host.lan_ssl(), base_url=f"https://{host.lan}:{host.port}", timeout=15) as client:
        refused = client.get("/api/actions/registry", headers={"Authorization": f"Bearer {paired['device_token']}"})
    assert refused.status_code == 401, refused.text


def test_release_bar_7_the_activity_stream_is_live_again_after_the_host_restarts(pair):
    """Engine half of #5912: after a Sharing switch restarts the host, a new subscriber to its activity stream (a device
    token minted before the restart still works) gets what happens next. The app half (the reconnect itself) is Swift."""
    host, guest = pair
    host.make_library("Reconnect bar")
    paired = _paired_guest_device(host, guest)
    before = _lan_stream(host, paired["device_token"])
    before.wait_open()
    host.restart(sharing=True)  # what the app does for a Sharing switch
    assert before.ended.wait(30), "the old stream outlived the engine it was connected to"
    after = _lan_stream(host, paired["device_token"])
    after.wait_open()
    assert after.wait_line(), "the new subscriber heard nothing (not even a keepalive) from the restarted host"


def test_release_bar_8_no_engine_death_on_any_sharing_or_multiuser_switch():
    """The engine half of #5909: what the app does for a switch is stop the engine and start it again with the new settings.
    Every combination, three times round, must come up, answer health on its socket (and on the LAN address exactly while
    Sharing is on), and still be running afterwards. The app-side race (a start already in flight) is Swift and is not
    reached from here (`sharing.switching-restarts-the-engine-once`)."""
    lan = engines.lan_address()
    if lan is None:
        pytest.skip("this Mac has no LAN address")
    host = engines.start_host(lan, sharing=False)
    try:
        for cycle in range(3):
            # Sharing on is the one switch for the LAN listener (5b44474cd); Multi-user is the engine's own setting, changed by
            # its route as the app does, and it must survive the Sharing restart that follows.
            for sharing, multiuser in ((True, False), (True, True), (False, True), (False, False)):
                if multiuser and not host._multiuser:
                    engines.turn_multiuser_on(host)
                elif not multiuser and host._multiuser:
                    engines.turn_multiuser_off(host)
                host.restart(sharing=sharing)
                where = f"cycle {cycle}, sharing={sharing}, multiuser={multiuser}"
                assert host.alive(), f"the engine died: {where}"
                with host.uds as local:
                    assert local.get("/api/health").status_code == 200, where
                assert host.lan_answers() is sharing, f"the LAN listener does not follow Sharing: {where}"
                assert host.alive(), f"the engine died after answering: {where}"
    finally:
        host.stop()

