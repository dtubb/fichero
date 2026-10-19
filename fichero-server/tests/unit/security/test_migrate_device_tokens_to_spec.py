"""multiuser.migrate-device-tokens (slice 5, #2403): paired devices become device clients, and their tokens keep working.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md. Each non-revoked `devices` row gets a `clients`
row (same id, same person, kind "device") with no key yet; the old token keeps working as that client's credential
until the device signs in by key (slice 7). A revoked device stays revoked, and revoking a device ends its client.

Built in slice 5.
"""

from fichero_server.security import accounts
from tests.signed_in import new_key, signature_for
from tests.unit.security.test_sharing_probe_2026_10_01 import _bearer, _multiuser_on, harness  # noqa: F401


def _device(harness, user, name, token):
    return harness.app_db.create_device(name=name, user_id=user.id, token_hash=accounts.hash_token(token))


def test_a_live_device_becomes_a_device_client_of_its_person(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    phone = _device(harness, users["alice"], "Alice's iPhone", "tok-phone")
    assert harness.app_db.migrate_device_tokens_to_clients() == 1
    client = harness.app_db.get_client(phone.id)
    assert (client.user_id, client.kind, client.name) == (users["alice"].id, "device", "Alice's iPhone")
    assert client.revoked_at is None


def test_a_revoked_device_is_not_migrated(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    old = _device(harness, users["alice"], "Old iPad", "tok-old")
    harness.app_db.revoke_device(old.id)
    assert harness.app_db.migrate_device_tokens_to_clients() == 0
    assert harness.app_db.get_client(old.id) is None


def test_running_the_migration_twice_adds_nothing(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    _device(harness, users["alice"], "Alice's iPhone", "tok-phone")
    assert harness.app_db.migrate_device_tokens_to_clients() == 1
    assert harness.app_db.migrate_device_tokens_to_clients() == 0


def test_the_old_token_keeps_working_after_the_migration(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    _device(harness, users["alice"], "Alice's iPhone", "tok-phone")
    harness.app_db.migrate_device_tokens_to_clients()
    identity = harness.client().get("/api/auth/identity", headers=_bearer("tok-phone"))
    assert identity.status_code == 200
    assert identity.json()["auth_kind"] == "device"


def test_a_migrated_device_has_no_key_so_nothing_signs_in_as_it(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    phone = _device(harness, users["alice"], "Alice's iPhone", "tok-phone")
    harness.app_db.migrate_device_tokens_to_clients()
    http = harness.client()
    issued = http.post("/api/auth/challenge", json={"client_id": phone.id})
    if issued.status_code == 200:
        key, _pem = new_key()
        refused = http.post(
            "/api/auth/sign-in",
            json={"client_id": phone.id, "nonce": issued.json()["nonce"], "signature": signature_for(key, phone.id, issued.json())},
        )
        assert refused.status_code == 401
    else:
        assert issued.status_code == 401


def test_revoking_the_device_revokes_its_client(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    phone = _device(harness, users["alice"], "Alice's iPhone", "tok-phone")
    harness.app_db.migrate_device_tokens_to_clients()
    harness.app_db.revoke_device(phone.id)
    assert harness.app_db.get_client(phone.id).revoked_at is not None


def test_a_failing_migration_never_stops_the_db_opening_and_old_tokens_still_work(tmp_path, monkeypatch):
    from fichero_server.db.app import AppDatabase

    def boom(self):
        raise RuntimeError("migration broke")

    monkeypatch.setattr(AppDatabase, "migrate_device_tokens_to_clients", boom)
    db = AppDatabase(tmp_path / "app.duckdb")  # must not raise
    try:
        user = db.create_user(
            username="alice", display_name="Alice", password_hash=accounts.hash_password("x"), is_owner=False
        )
        db.create_device(name="Alice's iPhone", user_id=user.id, token_hash=accounts.hash_token("tok-phone"))
        assert db.get_device_by_token_hash(accounts.hash_token("tok-phone")) is not None
    finally:
        db.close()
