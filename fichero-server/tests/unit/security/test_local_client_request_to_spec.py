"""multiuser.first-connection-asks-the-person (slice 6a, #2403): a local CLI/MCP client asks, the owner allows,
the client registers its own key.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md. Routes under `/api/auth/local-clients/`:
switches (owner, default off), request (Unix socket only, verified peer, switch on), requests + decision (the owner
signed in), register (the same program, once, after Allow). Nothing is on until the owner turns a switch on.
"""

import os

import pytest

from tests.signed_in import new_key, signature_for, signed_in_client, uds_client
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401

BASE = "/api/auth/local-clients"


@pytest.fixture(autouse=True)
def _no_requests_left_over_from_another_test():
    from fichero_server.api.routes.auth import accounts as routes

    routes._client_requests.clear()
    yield
    routes._client_requests.clear()
PEER = {"uid": os.getuid(), "pid": 4242, "token": "aa" * 32, "exe": "/usr/local/bin/fichero", "signer": "Fichero"}
ASK = {"kind": "cli", "name": "fichero CLI", "host": "MacBook Pro"}


def _owner(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    return users, signed_in_client(harness, users["owner"], kind="app", name="Fichero")


def _switch_on(harness, owner, **kinds):
    both = {"mcp": False, "cli": False, **kinds}
    done = harness.client().put(BASE + "/switches", json=both, headers=owner.headers)
    assert done.status_code == 200, done.text


def _ask(harness, peer=PEER, body=ASK):
    return uds_client(harness, peer).post(BASE + "/request", json=body)


def test_the_switches_start_off_and_only_the_signed_in_owner_changes_them(harness, monkeypatch):
    users, owner = _owner(harness, monkeypatch)
    assert harness.client().get(BASE + "/switches", headers=owner.headers).json() == {"mcp": False, "cli": False}
    alice = signed_in_client(harness, users["alice"])
    put = harness.client().put(BASE + "/switches", json={"mcp": True, "cli": True}, headers=alice.headers)
    assert put.status_code == 403
    _switch_on(harness, owner, cli=True)
    assert harness.client().get(BASE + "/switches", headers=owner.headers).json() == {"mcp": False, "cli": True}


def test_off_means_refused(harness, monkeypatch):
    _owner(harness, monkeypatch)
    refused = _ask(harness)
    assert refused.status_code == 403 and "not allowed on this Mac" in refused.text


def test_tcp_listener_refuses_client_routes(harness, monkeypatch):
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    assert harness.client().post(BASE + "/request", json=ASK).status_code == 403


def test_a_request_with_no_verified_peer_or_another_macos_user_is_refused(harness, monkeypatch):
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    assert _ask(harness, peer=None).status_code == 403
    assert _ask(harness, peer={**PEER, "uid": os.getuid() + 1}).status_code == 403


def test_request_records_verified_peer_not_claimed_name(harness, monkeypatch):
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    asked = _ask(harness, body={**ASK, "name": "Claude Code (MCP)"})
    assert asked.status_code == 200
    listed = harness.client().get(BASE + "/requests", headers=owner.headers).json()["items"]
    assert listed[0]["peer"] == {"pid": 4242, "exe": "/usr/local/bin/fichero", "signer": "Fichero"}
    assert listed[0]["state"] == "pending"
    alice = signed_in_client(harness, _users["alice"])
    assert harness.client().get(BASE + "/requests", headers=alice.headers).status_code == 403


def test_nothing_works_until_allow_then_the_client_registers_its_own_key_and_signs_in(harness, monkeypatch):
    users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    request_id = _ask(harness).json()["id"]
    key, pem = new_key()
    early = uds_client(harness, PEER).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert early.status_code == 409
    decided = harness.client().post(
        f"{BASE}/requests/{request_id}/decision", json={"allow": True}, headers=owner.headers
    )
    assert decided.json()["state"] == "allowed"
    done = uds_client(harness, PEER).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert done.status_code == 200, done.text
    client_id = done.json()["id"]
    assert harness.app_db.get_client(client_id).user_id == users["owner"].id
    http = harness.client()
    issued = http.post("/api/auth/challenge", json={"client_id": client_id}).json()
    signed = http.post(
        "/api/auth/sign-in",
        json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
    )
    assert signed.status_code == 200 and signed.json()["client"]["kind"] == "cli"
    again = uds_client(harness, PEER).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert again.status_code == 404


def test_deny_means_no_client(harness, monkeypatch):
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    request_id = _ask(harness).json()["id"]
    harness.client().post(f"{BASE}/requests/{request_id}/decision", json={"allow": False}, headers=owner.headers)
    _key, pem = new_key()
    refused = uds_client(harness, PEER).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert refused.status_code == 403


def test_another_program_cannot_register_for_an_allowed_request(harness, monkeypatch):
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    request_id = _ask(harness).json()["id"]
    harness.client().post(f"{BASE}/requests/{request_id}/decision", json={"allow": True}, headers=owner.headers)
    _key, pem = new_key()
    thief = {**PEER, "pid": 9999, "token": "bb" * 32, "exe": "/usr/bin/python3"}
    stolen = uds_client(harness, thief).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert stolen.status_code == 404


def test_the_bootstrap_token_is_not_the_owner_here(harness, monkeypatch):
    _owner(harness, monkeypatch)
    http = harness.client()
    assert http.get(BASE + "/switches", headers={"Authorization": "Bearer " + harness.bootstrap}).status_code == 403


def test_one_program_cannot_fill_the_owners_list(harness, monkeypatch):
    from fichero_server.api.routes.auth import accounts as routes

    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    codes = [_ask(harness).status_code for _ in range(routes.MAX_PENDING_PER_PROGRAM + 1)]
    assert codes[-1] == 429 and codes[:-1] == [200] * routes.MAX_PENDING_PER_PROGRAM
    other = {**PEER, "pid": 7, "token": "cc" * 32, "exe": "/usr/local/bin/other"}
    assert _ask(harness, peer=other).status_code == 200


def test_a_reused_pid_is_a_different_program(harness, monkeypatch):
    # Same pid and path, but the audit token (which carries the pid version) differs: not the program that asked.
    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    request_id = _ask(harness).json()["id"]
    harness.client().post(f"{BASE}/requests/{request_id}/decision", json={"allow": True}, headers=owner.headers)
    _key, pem = new_key()
    reused = {**PEER, "token": "dd" * 32}
    stolen = uds_client(harness, reused).post(BASE + "/register", json={"request_id": request_id, "public_key_pem": pem})
    assert stolen.status_code == 404


def test_a_peer_whose_program_cannot_be_read_is_refused_not_recorded(harness, monkeypatch):
    # Review r140f (1): a failed SecCode lookup gives exe "", which must not become a request the owner is asked to allow.
    from fichero_server.api import uds_peer
    from fichero_server.api.routes.auth import accounts as routes

    _users, owner = _owner(harness, monkeypatch)
    _switch_on(harness, owner, cli=True)
    unreadable = {"uid": os.getuid(), "pid": 4243, "token": "bb" * 32}  # no exe: identify() must look it up
    monkeypatch.setattr(uds_peer, "_code_identity", lambda token: ("", None))
    monkeypatch.setattr(uds_peer.sys, "platform", "darwin")
    refused = _ask(harness, peer=unreadable)
    assert refused.status_code == 403 and "could not be verified" in refused.text
    assert not routes._client_requests
