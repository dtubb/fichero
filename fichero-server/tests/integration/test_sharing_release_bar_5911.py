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
    # Multi-user on: the app's state, and the only one in which the host's owner signs in as a person to mint a code.
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
    with httpx.Client(verify=False, base_url=f"https://{host.lan}:{host.port}", timeout=15) as client:
        assert client.get("/api/health").status_code == 200


def test_release_bar_1_a_guest_pairs_over_the_lan_listener(pair):
    host, guest = pair
    with host.uds as local:
        minted = local.post("/api/pair/code")
        assert minted.status_code == 200, minted.text  # the host minted a link only because it listens where it names
        link = engines.pairing_link(host, minted.json()["code"])

    paired = engines.pair_with_link(guest, link)
    assert paired["device_token"] and paired["device_id"]

    with httpx.Client(verify=False, base_url=f"https://{host.lan}:{host.port}", timeout=15) as client:
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
            # TODO(#5908): once 5b44474cd (candidate 13) is in this base, turn Multi-user on through the route after the owner's
            # password is set, and assert it is refused without one; today the switch is the env the app gives the engine.
            # TODO(#5911): switch items 1 and 8 to the Sharing-on path (no separate "This network" switch) once 5b44474cd is in this base.
            for sharing, multiuser in ((True, False), (True, True), (False, True), (False, False)):
                host.restart(sharing=sharing, multiuser=multiuser)
                where = f"cycle {cycle}, sharing={sharing}, multiuser={multiuser}"
                assert host.alive(), f"the engine died: {where}"
                with host.uds as local:
                    assert local.get("/api/health").status_code == 200, where
                assert host.lan_answers() is sharing, f"the LAN listener does not follow Sharing: {where}"
                assert host.alive(), f"the engine died after answering: {where}"
    finally:
        host.stop()

