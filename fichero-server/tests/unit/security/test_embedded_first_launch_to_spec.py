"""multiuser.first-launch-creates-owner-and-key, as the EMBEDDED app lives it (#2403, overnight audit 2026-10-18).

The app's first authenticated request (the spawn wait) reaches the engine BEFORE sign-in runs, and with Multi-user
off the engine makes the owner row for it (`ensure_owner_account`, no key). So first-run is refused (409) on every
fresh install, and the app must put its key on that row with migrate-owner and then sign in by challenge.
"""

import pytest

from fichero_server.api.auth import initialize_token
from tests.signed_in import new_key, signature_for, uds_client
from tests.unit.security.test_sharing_probe_2026_10_01 import _bearer, harness  # noqa: F401

SECRET = "cd" * 32


@pytest.fixture(autouse=True)
def engine_secret():
    from fichero_server.security import launch_secret

    launch_secret.set_secret(SECRET)
    yield
    launch_secret.set_secret(None)


def _body(pem, *, display_name=None):
    body = {"public_key_pem": pem, "client": {"kind": "app", "name": "Fichero", "host": "MacBook Pro"}}
    return {**body, "display_name": display_name} if display_name else body


def test_the_first_loopback_request_makes_a_keyless_owner_so_first_run_is_409(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    assert not harness.app_db.list_users()
    ready = harness.client().get("/api/auth/identity", headers=_bearer(initialize_token()))
    assert ready.status_code == 200, ready.text
    owners = [user for user in harness.app_db.list_users() if user.is_owner]
    assert len(owners) == 1 and not harness.app_db.user_has_key(owners[0].id)
    _key, pem = new_key()
    refused = uds_client(harness).post(
        "/api/auth/first-run", json=_body(pem, display_name="Daniel"), headers={"X-Fichero-Launch-Secret": SECRET}
    )
    assert refused.status_code == 409


def test_migrate_owner_then_sign_in_works_on_that_row(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    harness.client().get("/api/auth/identity", headers=_bearer(initialize_token()))
    key, pem = new_key()
    http = uds_client(harness)
    migrated = http.post("/api/auth/migrate-owner", json=_body(pem), headers={"X-Fichero-Launch-Secret": SECRET})
    assert migrated.status_code == 200, migrated.text
    client_id = migrated.json()["client"]["id"]
    issued = http.post("/api/auth/challenge", json={"client_id": client_id}).json()
    signed = http.post(
        "/api/auth/sign-in",
        json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
    )
    assert signed.status_code == 200 and signed.json()["user"]["is_owner"] is True
    # Multi-user is still off: the bootstrap token keeps working for the app's other requests.
    assert harness.client().get("/api/auth/identity", headers=_bearer(initialize_token())).status_code == 200
