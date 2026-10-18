"""multiuser.audit-names-person-and-client (slice 2, #2403): every audit row says the person AND the client.

A session signed in through a client carries that client; the audit row's `device` names it ({id, name, kind}) next to
the person in `actor`, and a run's `started_by` reads "<client> for <person>" for a CLI or MCP client and
"<person> on <device>" for a device. 
"""

from fichero_server.actions.registry import ActionContext, started_by_for
from tests.unit.security.test_challenge_sign_in_to_spec import (  # noqa: F401
    _bearer,
    _issue,
    _new_key,
    _sign,
    _sign_in,
    alice_client,
    harness,
)

def _note_audits(harness):
    return [a for a in harness.audit_rows() if a.action_name == "note.create"]


def _sign_in_session(harness, client, key) -> str:
    issued = _issue(harness, client.id)
    signed = _sign_in(harness, client.id, issued, _sign(key, client.id, issued))
    assert signed.status_code == 200, signed.text
    return signed.json()["session_token"]


def test_a_note_made_through_a_signed_in_client_names_person_and_client(alice_client):
    harness, _users, key, client = alice_client
    token = _sign_in_session(harness, client, key)
    made = harness.client().post("/api/notes", json={"body": "from the phone"}, headers=_bearer(token))
    assert made.status_code == 200, made.text
    (row,) = _note_audits(harness)
    assert row.actor == "alice"
    assert row.device == {"id": client.id, "name": "Alice's iPhone", "kind": "device"}


def test_a_cli_client_is_named_for_its_person(alice_client):
    harness, users, _key, _client = alice_client
    key, pem = _new_key()
    cli = harness.app_db.create_client(
        user_id=users["alice"].id, kind="cli", name="fichero CLI", host="MacBook Pro", public_key_pem=pem
    )
    token = _sign_in_session(harness, cli, key)
    assert harness.client().post("/api/notes", json={"body": "from the CLI"}, headers=_bearer(token)).status_code == 200
    (row,) = _note_audits(harness)
    assert row.actor == "alice"
    assert row.device["kind"] == "cli" and row.device["name"] == "fichero CLI"


def test_started_by_reads_client_for_person_and_person_on_device():
    cli = ActionContext(actor="alice", device={"id": "c1", "name": "fichero CLI", "kind": "cli"})
    mcp = ActionContext(actor="daniel", device={"id": "c2", "name": "Claude Code (MCP)", "kind": "mcp"})
    phone = ActionContext(actor="alice", device={"id": "c3", "name": "Alice's iPhone", "kind": "device"})
    paired = ActionContext(actor="owner", device={"id": "d1", "name": "MBP"})  # an old device token: no kind
    here = ActionContext(actor="owner")
    assert started_by_for(cli) == "fichero CLI for alice"
    assert started_by_for(mcp) == "Claude Code (MCP) for daniel"
    assert started_by_for(phone) == "alice on Alice's iPhone"
    assert started_by_for(paired) == "owner on MBP"
    assert started_by_for(here) == "owner"
