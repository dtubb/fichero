"""`sharing.failure-names-the-step` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 2.1), the CLI's half.

The app's sentences live in one Swift table (`PairingFailure`). The CLI keeps its own few, in step by name: each refusal
carries the key phrase of its step, and none shows a bare code or a Python exception name.
"""
from __future__ import annotations

import re

import pytest

from fichero_cli import pairing
from fichero_cli.client import FicheroError

PIN = "c3BraS1waW4="


def _refusal(api_url, spki=PIN, fetch=lambda host, port: b"der"):
    with pytest.raises(FicheroError) as raised:
        pairing.check_trust(api_url, spki, fetch_der=fetch)
    return str(raised.value)


def _unreachable(host, port):
    raise OSError(61, "Connection refused")


@pytest.mark.parametrize("api_url, spki, fetch, phrase", [
    ("http://host.local:8765", PIN, None, "Ask the host for a new link"),                     # step 1: the link
    ("https://host.local:8765", None, None, "ask the host for a new link"),                    # step 5: no pin to check against
    ("https://host.local:8765", PIN, _unreachable, "Could not reach host.local"),              # step 3: reach
    ("https://host.local:8765", PIN, lambda h, p: b"other", "does not match the link's pin"),  # step 5: certificate
    ("https://100.64.0.1:8765", PIN, None, "work by name, not by number"),                     # step 5: a tailnet number
])
def test_each_refusal_carries_its_steps_key_phrase_and_no_code(api_url, spki, fetch, phrase):
    text = _refusal(api_url, spki, fetch or (lambda h, p: b"der"))
    assert phrase in text
    assert not re.search(r"\b-?\d{4}\b", text.replace("8765", "")), text  # no bare error code
    assert "Traceback" not in text and "Error(" not in text


def test_a_tailnet_name_needs_no_pin_and_is_not_refused():
    pairing.check_trust("https://m.tail1234.ts.net:8765", None)
