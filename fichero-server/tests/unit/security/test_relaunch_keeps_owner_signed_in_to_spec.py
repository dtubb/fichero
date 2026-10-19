"""multiuser.sign-in-by-challenge across relaunches and engine restarts (#2403, overnight audit 2026-10-18).

The app signs in again on every launch and after every engine restart, with the client id it remembered and the key in
the Keychain. That only works if the engine's client row, the key it holds and its own engine id all survive a restart.
"""

from fichero_server.api.routes.auth import accounts as routes
from fichero_server.db.app import AppDatabase
from fichero_server.security import accounts
from tests.signed_in import new_key, signature_for


def test_the_client_its_key_and_the_engine_id_survive_an_engine_restart(tmp_path):
    path = tmp_path / "app.duckdb"
    first = AppDatabase(path)
    owner = first.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True
    )
    key, pem = new_key()
    client = first.create_client(user_id=owner.id, kind="app", name="Fichero", host="Mac", public_key_pem=pem)
    engine_id = routes._engine_id(first)
    first.close()

    second = AppDatabase(path)  # the engine restarted
    assert routes._engine_id(second) == engine_id
    live = routes._live_client(second, client.id)
    assert live is not None and live.user_id == owner.id
    issued = {"nonce": "n", "expires_at": 4_000_000_000, "engine_id": engine_id}
    message = routes._sign_in_message(engine_id, client.id, "n", 4_000_000_000)
    assert routes._signature_is_valid(live.public_key_pem, message, signature_for(key, client.id, issued))
    second.close()


def test_a_second_launch_uses_the_same_client_not_a_new_one(tmp_path):
    # The app signs in again with the stored client id; nothing on the engine adds a client per launch.
    db = AppDatabase(tmp_path / "app.duckdb")
    owner = db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True
    )
    _key, pem = new_key()
    client = db.create_client(user_id=owner.id, kind="app", name="Fichero", host="Mac", public_key_pem=pem)
    for _ in range(3):
        assert routes._live_client(db, client.id) is not None
    assert db.user_has_key(owner.id)
    db.close()
