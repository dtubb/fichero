"""`sharing.cli-pairs-over-tailscale` (#5907, release bar #5910 item 2): `fichero devices pair` against a `.ts.net` link.

A `.ts.net` host is certified by a public authority behind `tailscale serve`: its link carries no pin (#5753) and the
CLI neither reads nor pins its certificate."""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import client as client_module
from fichero_cli import pairing

TAILNET = "https://studio.tail1234.ts.net"
TOKEN = "tailnet-device-token-secret"
GOOD = {"device_id": "dev-ts", "device_token": TOKEN, "expires_at": "2099-01-01T00:00:00Z"}


def link(api_url=TAILNET, spki=None) -> str:
    payload = {"v": 1, "api_url": api_url, "pair_code": "TAIL-CODE", "spki": spki, "library_path": "/x"}
    return "fichero://pair?payload=" + base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture
def pairing_rig(monkeypatch, tmp_path):
    """Record what the CLI opens and sends; fail loudly if it reads a certificate."""
    seen = {"opened": [], "sent": []}

    def open_client(api_url, uds, spki):
        seen["opened"].append((api_url, uds, spki))

        def handle(request):
            seen["sent"].append(json.loads(request.content))
            return httpx.Response(200, json=GOOD)
        return httpx.Client(base_url=api_url, transport=httpx.MockTransport(handle))

    def no_certificate_read(host, port):
        raise AssertionError(f"a .ts.net host's certificate must not be read or pinned ({host}:{port})")

    monkeypatch.setattr(pairing, "DEVICES_PATH", tmp_path / "paired-devices.json")
    monkeypatch.setattr(pairing, "_open_client", open_client)
    monkeypatch.setattr(pairing, "served_spki_der", no_certificate_read)
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return seen


def pair_command(tmp_path, text, *args):
    file = tmp_path / "link"
    file.write_text(text + "\n")
    return CliRunner().invoke(
        cli.app, ["devices", "pair", "--link-file", str(file), "--name", "this Mac", *args])


def test_the_command_pairs_over_a_ts_net_link_with_no_pin_and_never_prints_the_token(pairing_rig, tmp_path):
    out = pair_command(tmp_path, link())

    assert out.exit_code == 0, out.output
    assert TOKEN not in out.stdout + out.stderr
    assert "studio.tail1234.ts.net" in out.stdout and "dev-ts" in out.stdout
    assert pairing_rig["opened"] == [(TAILNET, None, None)], "system trust: no pin handed to the connection"
    assert pairing_rig["sent"] == [{"code": "TAIL-CODE", "device_name": "this Mac"}], "no username or password"


def test_a_pin_a_ts_net_link_carries_anyway_is_discarded_not_trusted(pairing_rig, tmp_path):
    out = pair_command(tmp_path, link(spki=base64.b64encode(b"a-key-that-cannot-describe-the-public-cert").decode()))

    assert out.exit_code == 0, out.output
    assert pairing_rig["opened"][0][2] is None
    stored = pairing._read_store()[client_module.engine_key(TAILNET, None)]
    assert stored["spki"] is None and stored["device_token"] == TOKEN


def test_the_stored_token_is_used_for_that_host_with_system_trust(pairing_rig, tmp_path):
    pair_command(tmp_path, link())
    key = client_module.engine_key(TAILNET, None)

    assert client_module._read_token(base_url=TAILNET, engine=key) == TOKEN
    assert pairing.pinned_context(TAILNET) is None, "no pin stored: later calls use the system's trust"


def test_http_for_a_ts_net_name_is_refused(pairing_rig, tmp_path):
    out = pair_command(tmp_path, link(api_url="http://studio.tail1234.ts.net"))

    assert out.exit_code == 1
    assert "plain http" in out.stderr
    assert pairing_rig["sent"] == []
    assert not (tmp_path / "paired-devices.json").exists()


@pytest.mark.parametrize("lookalike", [
    "https://evil.ts.net.example.com",
    "https://evilts.net",
    "https://studio.tail1234.ts.net.",
    "https://studio.tail1234.ts.net.evil.example",
])
def test_a_lookalike_of_a_ts_net_name_is_not_system_trust_and_needs_the_pin(pairing_rig, tmp_path, lookalike):
    out = pair_command(tmp_path, link(api_url=lookalike, spki=None))

    assert out.exit_code == 1
    assert "no certificate pin" in out.stderr
    assert pairing_rig["sent"] == []


def test_a_ts_net_name_on_another_port_is_still_system_trust(pairing_rig, tmp_path):
    out = pair_command(tmp_path, link(api_url=TAILNET + ":8443"))
    assert out.exit_code == 0, out.output
    assert pairing_rig["opened"][0][2] is None
