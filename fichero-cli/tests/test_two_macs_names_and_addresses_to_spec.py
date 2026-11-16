"""`sharing.client-tries-every-address`, `sharing.ios-link-has-one-address` (docs/contributor_manual/specs/source/sharing-two-macs.md
§4, Step 2.3), the CLI's half.

A link with several addresses is tried one after another in its order, each within 5 seconds, and the code goes to the first
that passes the trust check and answers. The person reads which one answered and why each earlier one did not; a bare timeout or
a code never reaches them.
"""
from __future__ import annotations

import base64
import json

import httpx
import pytest

from fichero_cli import pairing
from fichero_cli.client import FicheroError

PIN = base64.b64encode(b"the-hosts-public-key").decode()
LOCAL = "https://m.local:8765"
LAN = "https://192.0.2.10:8765"
TAIL = "https://m.tail1234.ts.net:8765"


def _link(api_url, alts, code="ABC123"):
    return pairing.PairLink(api_url=api_url, code=code, spki=PIN, alt_urls=tuple(alts))


def _good_der(host, port):
    return b"the-hosts-public-key"


class Probe:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def __call__(self, url, spki):
        self.asked.append((url, spki))
        return self.answers[url]


def test_the_second_address_is_used_when_the_first_does_not_answer_and_both_are_named():
    probe = Probe({LOCAL: "this Mac cannot find that name on this network", TAIL: None})
    chosen, notes = pairing.reach(_link(LOCAL, [TAIL, LAN]), probe=probe, fetch_der=_good_der)
    assert chosen == TAIL
    assert [u for u, _ in probe.asked] == [LOCAL, TAIL]  # in the link's order, stopping at the first that answered
    assert notes[0] == "Connected through Tailscale (m.tail1234.ts.net)."
    assert "m.local address did not answer: this Mac cannot find that name on this network." in notes[1]


def test_a_tailnet_address_is_asked_without_a_pin_and_a_local_one_with_it():
    probe = Probe({TAIL: "no answer in 5 s", LAN: None})
    pairing.reach(_link(TAIL, [LAN]), probe=probe, fetch_der=_good_der)
    assert probe.asked == [(TAIL, None), (LAN, PIN)]


def test_when_none_answers_every_attempt_is_named_in_one_sentence():
    probe = Probe({LOCAL: "this Mac cannot find that name on this network",
                   TAIL: "no answer in 5 s: is Tailscale on this Mac?", LAN: "no answer in 5 s: the network may keep devices apart"})
    with pytest.raises(FicheroError) as raised:
        pairing.reach(_link(LOCAL, [TAIL, LAN]), probe=probe, fetch_der=_good_der)
    text = str(raised.value)
    assert text.startswith("Could not reach m.local. Tried ")
    assert "Tailscale (m.tail1234.ts.net): no answer in 5 s: is Tailscale on this Mac?" in text and "192.0.2.10:" in text
    assert "-1001" not in text and "timed out" not in text.lower()  # no bare transport words or codes


def test_an_address_whose_certificate_does_not_match_is_skipped_not_trusted():
    def der(host, port):
        return b"someone-else" if host == "m.local" else b"the-hosts-public-key"
    probe = Probe({LOCAL: None, LAN: None})
    chosen, notes = pairing.reach(_link(LOCAL, [LAN]), probe=probe, fetch_der=der)
    assert chosen == LAN and [u for u, _ in probe.asked] == [LAN]  # the mismatched one was never asked for the code's sake
    assert "does not match the link's pin" in notes[1]


def test_at_most_three_addresses_are_tried():
    four = [f"https://192.0.2.{n}:8765" for n in range(10, 14)]
    probe = Probe({u: "no answer in 5 s" for u in four})
    with pytest.raises(FicheroError):
        pairing.reach(_link(four[0], four[1:]), probe=probe, fetch_der=_good_der)
    assert len(probe.asked) == pairing.MAX_LINK_ADDRESSES


def test_the_real_probe_gives_the_budget_and_words_for_a_timeout(monkeypatch):
    seen = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path, timeout=None):
            seen["timeout"] = timeout
            raise httpx.ConnectTimeout("t")

    monkeypatch.setattr(pairing, "_open_client", lambda url, uds, spki: Client())
    assert pairing._health_probe(TAIL, None) == "no answer in 5 s: is Tailscale on this Mac?"
    assert pairing._health_probe(LAN, PIN) == "no answer in 5 s: the network may keep devices apart"
    assert seen["timeout"] == 5.0


def test_the_code_goes_only_to_the_address_that_answered(monkeypatch, tmp_path):
    """pair() on a link whose first address is dead redeems at the second, and says so."""
    sent = []

    def handle(request):
        sent.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"device_id": "dev-1", "device_token": "t", "expires_at": "2099-01-01T00:00:00Z"})

    monkeypatch.setattr(pairing, "_open_client", lambda url, uds, spki: httpx.Client(base_url=url, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(pairing, "DEVICES_PATH", tmp_path / "devices.json")
    payload = {"v": 1, "api_url": LOCAL, "alt_urls": [TAIL], "pair_code": "ABC123", "spki": PIN, "library_path": "/x"}
    text = "fichero://pair?payload=" + base64.b64encode(json.dumps(payload).encode()).decode()
    done = pairing.pair(text, fetch_der=_good_der,
                        probe=lambda url, spki: "this Mac cannot find that name on this network" if url == LOCAL else None)
    assert [u for u, _ in sent] == [TAIL + "/api/pair"] and sent[0][1]["code"] == "ABC123"
    assert done["host"] == "m.tail1234.ts.net" and done["notes"][0].startswith("Connected through Tailscale")
