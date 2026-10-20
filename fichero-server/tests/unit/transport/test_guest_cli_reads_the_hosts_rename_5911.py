"""sharing.rename-reaches-the-other-side (#5911, release bar #5910 item 3), the CLI half.

The guest is the real CLI client (`FicheroClient`) holding only the device token that the real `fichero devices pair`
code path (`pairing.pair`) stored; the host is the engine in process, its own side signed in as the owner (no ambient
key). A rename on one side is the name the other side reads."""
import json

import httpx
import pytest

from fichero_cli import client as client_module
from fichero_cli import pairing
from fichero_cli.client import FicheroClient
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    SPKI_PIN,
    _bearer,
    _clear_pairing_state,
    _login,
    _multiuser_on,
    harness,
)

GUEST_URL = "https://paired.example"
PIN_KEY = b"spki-pin"  # SPKI_PIN is base64("spki-pin")


def _through(test_client):
    """An httpx transport that hands each request to the in-process engine over `test_client`'s connection."""

    def handle(request: httpx.Request) -> httpx.Response:
        sent = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
        answer = test_client.request(request.method, request.url.raw_path.decode(), content=request.content, headers=sent)
        return httpx.Response(answer.status_code, content=answer.content,
                              headers={"content-type": answer.headers.get("content-type", "application/json")})

    return httpx.MockTransport(handle)


@pytest.fixture
def two_macs(harness, monkeypatch, tmp_path):
    _multiuser_on(harness, monkeypatch)
    host = harness.client()
    host.headers.update(_bearer(_login(harness, "owner")))

    monkeypatch.setattr(pairing, "DEVICES_PATH", tmp_path / "paired-devices.json")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    guest_wire = harness.remote()  # the LAN listener: a non-loopback address
    monkeypatch.setattr(pairing, "_open_client",
                        lambda api_url, uds, spki: httpx.Client(base_url=api_url, transport=_through(guest_wire)))

    code = host.post("/api/pair/code").json()["code"]
    payload = json.dumps({"v": 1, "api_url": GUEST_URL, "pair_code": code, "spki": SPKI_PIN}).encode()
    import base64

    link = "fichero://pair?payload=" + base64.b64encode(payload).decode()
    pairing.pair(link, device_name="guest CLI", fetch_der=lambda h, p: PIN_KEY)
    guest = FicheroClient(base_url=GUEST_URL, transport=_through(guest_wire))
    assert guest.token, "the guest holds the device token the command stored"
    return host, guest


def _document(host, name):
    made = host.post("/api/documents", json={"name": name, "doc_type": "folder"})
    assert made.status_code in (200, 201), made.text
    return made.json()["id"]


def test_a_rename_on_the_host_is_what_the_guests_cli_reads(two_macs):
    host, guest = two_macs
    doc_id = _document(host, "Letters")
    assert guest.get_document(doc_id).name == "Letters"

    renamed = host.put(f"/api/documents/{doc_id}", json={"name": "Letters, renamed on the host"})
    assert renamed.status_code == 200, renamed.text
    assert guest.get_document(doc_id).name == "Letters, renamed on the host"


def test_a_rename_the_guest_makes_with_the_cli_is_what_the_host_reads(two_macs):
    host, guest = two_macs
    doc_id = _document(host, "Diaries")

    guest.update_document(doc_id, name="Diaries, renamed by the guest")
    assert host.get(f"/api/documents/{doc_id}").json()["name"] == "Diaries, renamed by the guest"
