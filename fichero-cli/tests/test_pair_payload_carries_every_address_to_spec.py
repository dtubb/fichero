"""`sharing.link-carries-every-address`, `sharing.ios-qr-payload-size` (docs/contributor_manual/specs/source/sharing-two-macs.md §4,
Step 1.7).

The pairing payload carries the chosen address first and the others as `alt_urls`, from the engine's own list
(`GET /api/pair/addresses`): never loopback, at most three addresses, each with its own trust rule (a `.ts.net` name is system
trust and needs no pin; the one `spki` pin rides if any address serves the engine's own certificate). An old client ignores
`alt_urls`; an old link has none. The QR form leaves the library path out and stays within 400 characters of payload.
"""
from __future__ import annotations

import base64
import json

from fichero_cli import pairing

TAIL = "https://m.tail1234.ts.net:8765"
LOCAL = "https://m.local:8765"
LAN = "https://192.0.2.10:8765"
PIN = "c3BraS1waW4="
ROWS = [
    {"kind": "tailnet", "url": "https://m.tail1234.ts.net", "listening": True, "reason": None},
    {"kind": "local-name", "url": LOCAL, "listening": True, "reason": None},
    {"kind": "lan", "url": LAN, "listening": True, "reason": None},
]


def _payload(text):
    return json.loads(pairing._payload_of(text))


def test_the_other_addresses_follow_the_chosen_one_in_the_engines_order():
    alts = pairing.alt_urls_from(ROWS, chosen=TAIL, sharing_address=LOCAL)
    assert alts == [LOCAL, LAN]  # the tailnet is the chosen one; the engine's order is kept; the port is the sharing port
    text = pairing.invite_link(api_url=TAIL, code="ABCD-1234", spki=PIN, expires_at=None, library_path=None, alt_urls=alts)
    payload = _payload(text)
    assert payload["api_url"] == TAIL and payload["alt_urls"] == [LOCAL, LAN]
    assert payload["spki"] == PIN  # the local names serve the engine's own certificate, so the pin rides
    assert list(payload) == sorted(payload)


def test_a_tailnet_only_link_carries_no_pin_even_with_alt_urls():
    text = pairing.invite_link(api_url=TAIL, code="C", spki=PIN, expires_at=None, library_path=None,
                               alt_urls=["https://other.tail1234.ts.net:8765"])
    assert "spki" not in _payload(text)


def test_a_row_that_cannot_work_or_a_loopback_address_is_never_carried():
    rows = ROWS + [{"kind": "lan", "url": "https://127.0.0.1:8765", "listening": True, "reason": None},
                   {"kind": "lan", "url": "https://localhost:8765", "listening": True, "reason": None}]
    rows[0] = dict(rows[0], listening=False, reason="Port 8765 on your tailnet already goes to x")
    assert pairing.alt_urls_from(rows, chosen=LOCAL, sharing_address=LOCAL) == [LAN]


def test_at_most_three_addresses_in_all_and_none_twice():
    rows = ROWS + [{"kind": "lan", "url": "https://192.0.2.11:8765", "listening": True, "reason": None}]
    alts = pairing.alt_urls_from(rows, chosen=LOCAL, sharing_address=LOCAL)
    assert len(alts) == 2 and LOCAL not in alts


def test_an_old_link_has_no_alt_urls_and_parses():
    text = pairing.invite_link(api_url=LOCAL, code="C", spki=PIN, expires_at=None, library_path=None)
    assert "alt_urls" not in _payload(text)
    link = pairing.parse_link(text)
    assert link.alt_urls == () and link.api_url == LOCAL


def test_a_new_link_parses_with_its_addresses_and_an_old_reader_still_gets_the_chosen_one():
    text = pairing.invite_link(api_url=TAIL, code="C", spki=PIN, expires_at=None, library_path=None, alt_urls=[LOCAL, LAN])
    link = pairing.parse_link(text)
    assert link.api_url == TAIL and link.alt_urls == (LOCAL, LAN)


def test_the_qr_form_leaves_out_the_library_path_and_fits_400_characters():
    long_path = "/Users/Shared/someone/Library/Application Support/Fichero/" + "a" * 200 + ".fichero"
    text = pairing.invite_link(api_url=TAIL, code="ABCD-1234", spki=PIN, expires_at="2026-11-02T20:00:00Z",
                               library_path=long_path, alt_urls=[LOCAL, LAN], for_qr=True)
    raw = text.split("payload=", 1)[1]
    from urllib.parse import unquote

    encoded = unquote(raw)
    assert len(encoded) <= 400
    assert "library_path" not in _payload(text)
    assert base64.b64decode(encoded)  # still a payload


def test_the_qr_form_drops_addresses_from_the_end_rather_than_overflow():
    many = [f"https://very-long-host-name-number-{i}.example.test.ts.net:8765" for i in range(3)]
    text = pairing.invite_link(api_url=TAIL, code="ABCD-1234", spki=PIN, expires_at="2026-11-02T20:00:00Z",
                               library_path=None, alt_urls=many, for_qr=True)
    from urllib.parse import unquote

    assert len(unquote(text.split("payload=", 1)[1])) <= 400
    assert _payload(text)["api_url"] == TAIL  # the chosen address is never the one dropped
