"""multiuser.env-without-owner-password-starts-off (#5908): an engine started with FICHERO_MULTIUSER on while no owner password was
ever chosen starts with Multi-user OFF, says why through health, and never exits. Red before `gate_env_at_start` existed."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fichero_server import startup_warnings
from fichero_server.api import main as api_main
from fichero_server.security import accounts, multiuser


def _owner(app_db, *, chose_password: bool):
    owner = app_db.create_user(username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True)
    if chose_password:
        multiuser.note_owner_password_set(app_db)
    return owner


def _env(**extra):
    return {"FICHERO_MULTIUSER": "1", multiuser.GATE_ENV_FLAG: "1", **extra}


def test_the_env_on_with_no_chosen_password_starts_off_and_says_why(app_db):
    _owner(app_db, chose_password=False)
    env = _env()
    words = multiuser.gate_env_at_start(app_db, env)
    assert words == multiuser.ENV_OFF_WORDS
    assert env["FICHERO_MULTIUSER"] == "0"
    assert multiuser.multiuser_enabled(env) is False


def test_the_env_on_with_a_chosen_password_stays_on(app_db):
    _owner(app_db, chose_password=True)
    env = _env()
    assert multiuser.gate_env_at_start(app_db, env) is None
    assert multiuser.multiuser_enabled(env) is True


def test_no_owner_yet_starts_off_too(app_db):
    env = _env()
    assert multiuser.gate_env_at_start(app_db, env) == multiuser.ENV_OFF_WORDS
    assert multiuser.multiuser_enabled(env) is False


def test_tests_and_dev_servers_that_do_not_set_the_engine_flag_are_untouched(app_db):
    _owner(app_db, chose_password=False)
    env = {"FICHERO_MULTIUSER": "1"}
    assert multiuser.gate_env_at_start(app_db, env) is None and env["FICHERO_MULTIUSER"] == "1"


def test_env_off_is_left_alone(app_db):
    env = _env(FICHERO_MULTIUSER="0")
    assert multiuser.gate_env_at_start(app_db, env) is None


def test_the_reason_reaches_health_in_words_only():
    startup_warnings.set_multiuser_words(multiuser.ENV_OFF_WORDS)
    try:
        assert startup_warnings.as_dependencies()["multiuser"] == multiuser.ENV_OFF_WORDS
    finally:
        startup_warnings.set_multiuser_words(None)
    assert "multiuser" not in startup_warnings.as_dependencies()


async def _never_runs() -> None:
    return None


def test_the_lifespan_runs_the_gate_at_start_up_and_health_says_why(app_db, monkeypatch):
    """Not only the helper: the engine's start-up (lifespan) calls it, so a start with the env on and no chosen password
    reports Multi-user off through GET /api/health."""
    _owner(app_db, chose_password=False)
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv(multiuser.GATE_ENV_FLAG, "1")
    monkeypatch.setattr(api_main, "get_app_db", lambda: app_db)
    monkeypatch.setattr(api_main, "_seed_builtin_providers", lambda: None)
    monkeypatch.setattr(api_main, "_collapse_duplicate_providers", lambda: None)
    monkeypatch.setattr(api_main, "_watch_parent_process", _never_runs)
    monkeypatch.setattr(api_main, "start_periodic_snapshot_task", lambda: None)
    monkeypatch.setattr(api_main, "stop_periodic_snapshot_task", lambda task: _never_runs())
    try:
        with TestClient(api_main.app) as client:
            body = client.get("/api/health").json()
        assert body["dependencies"].get("multiuser") == multiuser.ENV_OFF_WORDS, body
        assert multiuser.multiuser_enabled() is False
    finally:
        startup_warnings.set_multiuser_words(None)
