"""sharing.rename-reaches-the-other-side (#5911, release bar #5910 item 3), the CLI half.

The guest is the real CLI client (`FicheroClient`) holding only the device token that the real `fichero devices pair`
code path (`pairing.pair`) stored; the host is the engine in process, its own side signed in as the owner (no ambient
key). The code is minted for a NAMED person (person-bound invite), so the guest acts as that person: an editor's
rename is audited as the editor and the guest device, a viewer's is refused. A rename on one side is the name the other
side reads."""
import base64
import json

import httpx
import pytest

from fichero_cli import client as client_module
from fichero_cli import pairing
from fichero_cli.client import FicheroClient, FicheroError
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


def _through(test_client, sent_tokens=None):
    """An httpx transport that hands each request to the in-process engine over `test_client`'s connection and gives
    back everything the engine answered, headers included. `sent_tokens` collects the bearer each request carried."""

    def handle(request: httpx.Request) -> httpx.Response:
        sent = {k: v for k, v in request.headers.items() if k.lower() not in {"host", "content-length"}}
        if sent_tokens is not None:
            sent_tokens.append(sent.get("authorization"))
        answer = test_client.request(request.method, request.url.raw_path.decode(), content=request.content, headers=sent)
        kept = {k: v for k, v in answer.headers.items()
                if k.lower() not in {"content-length", "content-encoding", "transfer-encoding"}}
        return httpx.Response(answer.status_code, content=answer.content, headers=kept)

    return httpx.MockTransport(handle)


@pytest.fixture
def two_macs(harness, monkeypatch, tmp_path):
    users = _multiuser_on(harness, monkeypatch)
    host = harness.client()
    host.headers.update(_bearer(_login(harness, "owner")))

    monkeypatch.setattr(pairing, "DEVICES_PATH", tmp_path / "paired-devices.json")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    guest_wire = harness.remote()  # the LAN listener: a non-loopback address
    monkeypatch.setattr(pairing, "_open_client",
                        lambda api_url, uds, spki: httpx.Client(base_url=api_url, transport=_through(guest_wire)))

    def guest_as(person):
        """A guest Mac paired by a code minted for `person`, with the CLI's own stored token."""
        url = f"https://{person}-mac.example"
        code = host.post("/api/pair/code", json={"username": person}).json()["code"]
        payload = json.dumps({"v": 1, "api_url": url, "pair_code": code, "spki": SPKI_PIN}).encode()
        link = "fichero://pair?payload=" + base64.b64encode(payload).decode()
        pairing.pair(link, device_name="guest CLI", fetch_der=lambda h, p: PIN_KEY,
                     ask_person=lambda: (person, "pw-" + person))  # an invited existing person proves who they are
        sent = []
        guest = FicheroClient(base_url=url, transport=_through(guest_wire, sent))
        stored = pairing.device_token(client_module.engine_key(url, None))
        assert stored and guest.token == stored, "the guest holds the device token the command stored"
        return guest, stored, sent

    return host, guest_as, users


def _document(host, name):
    made = host.post("/api/documents", json={"name": name, "doc_type": "folder"})
    assert made.status_code in (200, 201), made.text
    return made.json()["id"]


def test_a_rename_on_the_host_is_what_the_guests_cli_reads(two_macs):
    host, guest_as, _ = two_macs
    guest, stored, sent = guest_as("alice")
    doc_id = _document(host, "Letters")
    assert guest.get_document(doc_id).name == "Letters"

    renamed = host.put(f"/api/documents/{doc_id}", json={"name": "Letters, renamed on the host"})
    assert renamed.status_code == 200, renamed.text
    assert guest.get_document(doc_id).name == "Letters, renamed on the host"
    assert set(sent) == {f"Bearer {stored}"}, "every guest request carried the stored device token and nothing else"


def test_an_editor_guests_rename_is_what_the_host_reads_and_is_audited_as_that_person_and_device(harness, two_macs):
    host, guest_as, _ = two_macs
    guest, _stored, _sent = guest_as("alice")  # alice is an editor
    doc_id = _document(host, "Diaries")
    before = {a.id for a in harness.audit_rows()}

    guest.update_document(doc_id, name="Diaries, renamed by the guest")

    assert host.get(f"/api/documents/{doc_id}").json()["name"] == "Diaries, renamed by the guest"
    rows = [a for a in harness.audit_rows() if a.id not in before and a.action_name == "document.update"]
    assert len(rows) == 1
    assert rows[0].actor == "alice", "acts as the person the code was minted for, never the owner who minted it"
    assert rows[0].device and rows[0].device["name"] == "guest CLI"


def test_a_viewer_guest_reads_but_its_rename_is_refused(two_macs):
    host, guest_as, _ = two_macs
    guest, _stored, _sent = guest_as("bob")  # bob is a viewer
    doc_id = _document(host, "Ledgers")

    assert guest.get_document(doc_id).name == "Ledgers"
    with pytest.raises(FicheroError) as refused:
        guest.update_document(doc_id, name="Ledgers, renamed by a viewer")
    assert refused.value.status_code == 403
    assert host.get(f"/api/documents/{doc_id}").json()["name"] == "Ledgers"


def test_a_new_person_invited_by_name_chooses_their_password_in_the_cli_and_is_that_person(harness, two_macs):
    """An invitation for a name with no account: `fichero devices pair` asks the person for a password of their own
    (never taken from the host), the account is made at the redeem and the device acts as them."""
    host, _guest_as, _users = two_macs
    code = host.post("/api/pair/code", json={"username": "newbie", "display_name": "Newbie"}).json()["code"]
    url = "https://newbie-mac.example"
    payload = json.dumps({"v": 1, "api_url": url, "pair_code": code, "spki": SPKI_PIN}).encode()
    link = "fichero://pair?payload=" + base64.b64encode(payload).decode()

    pairing.pair(link, device_name="guest CLI", fetch_der=lambda h, p: PIN_KEY, ask_new_password=lambda: "a long secret")

    person = harness.app_db.get_user_by_username("newbie")
    assert person is not None and person.display_name == "Newbie" and person.is_owner is False
    assert pairing.device_token(client_module.engine_key(url, None))
    assert harness.client().post("/api/auth/login", json={"username": "newbie", "password": "a long secret"}).status_code == 200
