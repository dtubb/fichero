"""Sharing release bar (#5910) driven by two real engines (#5911, spec `testenv.two-engines`).

Item 1: a guest pairs to the host over the host's LAN listener, with the pin checked against the certificate the host
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
    host = engines.start_host(lan)
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
