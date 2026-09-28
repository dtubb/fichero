"""Live generated-CLI coverage for multiuser auth, authz, pairing, and policy surfaces."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration._engine_wait import _wait_healthy  # (#5187)
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.db.app import AppDatabase
from fichero_cli import client as client_module

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

runner = CliRunner()


def _cli_multiuser_contracts_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_MULTIUSER_CONTRACTS") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_multiuser_contracts_ready(),
    reason="Generated CLI multiuser contracts are opt-in and require loopback socket access",
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _cli_json(live_engine, *args: str):
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _cli_result(live_engine, *args: str):
    return runner.invoke(
        cli.app,
        [
            "--json",
            "--base-url",
            live_engine["base_url"],
            "--library",
            str(live_engine["library"]),
            *args,
        ],
    )


def _login(monkeypatch: pytest.MonkeyPatch, live_engine, username: str, password: str):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: password)
    return _cli_json(live_engine, "auth", "login", username)


def _isolate_cli_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / ".missing-api-key")
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)


@pytest.fixture(scope="module")
def cli_multiuser_engine(tmp_path_factory):
    from tests.integration._seedlib import seed
    from tests.integration._cli_live import REPO_ROOT

    workdir = tmp_path_factory.mktemp("cli-multiuser")
    home = workdir / "home"
    home.mkdir()
    base = workdir / "base"
    base.mkdir()
    library = workdir / "library.fichero"
    summary = seed(library)

    app_db = AppDatabase(path=base / "app.duckdb")
    owner = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("secret"),
        is_owner=True,
    )
    app_db.set_library_role(
        user_id=owner.id,
        library_path=authz.normalize_library_path(str(library)),
        role=authz.ROLE_OWNER,
    )
    app_db.close()

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": str(REPO_ROOT / "fichero-server" / "src"),
        "FICHERO_DISABLE_AUTH": "0",
        "FICHERO_MULTIUSER": "1",
        "FICHERO_FEATURE_TIER": "dev",
        "FICHERO_SKIP_DEFAULT_WORKFLOWS": "1",
        "FICHERO_BASE_PATH": str(base),
        "FICHERO_PARENT_PID": str(os.getpid()),
    }
    uvicorn = Path(sys.executable).parent / "uvicorn"
    engine_log = workdir / "engine.log"
    log_handle = open(engine_log, "w")
    process = subprocess.Popen(
        [str(uvicorn), "fichero_server.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log_handle,
    )
    try:
        why = _wait_healthy(base_url, process)
        if why:
            tail = engine_log.read_text(errors="replace")[-4000:]
            pytest.fail(
                f"spawned multiuser engine never became healthy: {why}.\n"
                f"--- engine stderr (tail) ---\n{tail}"
            )
        yield {
            "base_url": base_url,
            "engine_log": engine_log,
            "library": library,
            "owner_id": owner.id,
            "summary": summary,
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        log_handle.close()


def test_generated_multiuser_auth_policy_pairing_contracts_current_main(
    cli_multiuser_engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cli_credentials(monkeypatch, tmp_path)

    owner = _login(monkeypatch, cli_multiuser_engine, "alice", "secret")
    assert owner["username"] == "alice"
    # On loopback the CLI is the owner unless an account is NAMED (loopback is always owner): a
    # stored session is read only for `--as-user`. So every call as alice names her.
    whoami = _cli_json(cli_multiuser_engine, "--as-user", "alice", "auth", "whoami")
    assert whoami["username"] == "alice"

    bob = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "users",
        "create",
        "--username",
        "bob",
        "--display-name",
        "Bob",
        "--password",
        "bob-secret",
    )
    assert bob["username"] == "bob"
    listed_users = _cli_json(cli_multiuser_engine, "--as-user", "alice", "users", "list")
    assert {item["username"] for item in listed_users["items"]} >= {"alice", "bob"}

    owner_snapshot = _cli_json(cli_multiuser_engine, "--as-user", "alice", "authz", "get-library-snapshot")
    assert owner_snapshot["current_user_role"] == "owner"
    assert owner_snapshot["can_manage_roles"] is True
    assert len(owner_snapshot["roles"]) == 1

    updated_members = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "authz",
        "set-library-member-role",
        "--user",
        "bob",
        "--role",
        "viewer",
    )
    assert any(member["username"] == "bob" and member["role"] == "viewer" for member in updated_members["members"])
    share = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "authz",
        "share-library-object",
        "--user",
        "bob",
        "--object-type",
        "document",
        "--object-id",
        cli_multiuser_engine["summary"]["keys"]["doc_letter"],
    )
    assert share["object_type"] == "document"
    assert share["share_url"].endswith(f"/api/documents/{cli_multiuser_engine['summary']['keys']['doc_letter']}")

    pairing_code = _cli_json(cli_multiuser_engine, "--as-user", "alice", "pair", "create-pairing-code")
    paired_device = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "pair",
        "device",
        "--code",
        pairing_code["code"],
        "--device-name",
        "CLI Phone",
    )
    listed_devices = _cli_json(cli_multiuser_engine, "--as-user", "alice", "pair", "list-devices")
    assert any(item["id"] == paired_device["device_id"] for item in listed_devices["items"])
    revoked_device = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "pair",
        "revoke-device",
        paired_device["device_id"],
    )
    assert revoked_device["status"] == "ok"

    created_rule = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "policies",
        "create-a-new-rule",
        "--name",
        "Require evidence",
        "--action",
        "require_approval",
        "--entity-type",
        "claims",
        "--min-evidence-count",
        "2",
        "--requires-source",
    )
    listed_rules = _cli_json(cli_multiuser_engine, "--as-user", "alice", "policies", "list-orchestration-rules")
    assert any(item["id"] == created_rule["id"] for item in listed_rules["rules"])
    fetched_rule = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "policies",
        "get-a-specific-rule",
        created_rule["id"],
    )
    assert fetched_rule["name"] == "Require evidence"
    evaluated_rule = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "policies",
        "evaluate-a-hypothetical-write-against",
        "--entity-type",
        "claims",
        "--evidence-count",
        "0",
        "--no-has-source",
    )
    assert evaluated_rule["action"] == "require_approval"
    updated_rule = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "policies",
        "update-a-rule",
        created_rule["id"],
        "--body",
        json.dumps({"description": "updated rule", "priority": 50}),
    )
    assert updated_rule["description"] == "updated rule"
    assert updated_rule["priority"] == 50
    deleted_rule = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "policies",
        "delete-a-rule",
        created_rule["id"],
        "--yes",
    )
    assert deleted_rule is None

    activities = _cli_json(cli_multiuser_engine, "--as-user", "alice", "activity-api", "list-activities")
    assert activities["count"] == 0


def test_generated_multiuser_fail_closed_contracts_current_main(
    cli_multiuser_engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate_cli_credentials(monkeypatch, tmp_path)

    _login(monkeypatch, cli_multiuser_engine, "alice", "secret")
    viewer = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "users",
        "create",
        "--username",
        "carol",
        "--display-name",
        "Carol",
        "--password",
        "carol-secret",
    )
    _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "authz",
        "set-library-member-role",
        "--user",
        "carol",
        "--role",
        "viewer",
    )

    _login(monkeypatch, cli_multiuser_engine, "carol", "carol-secret")
    viewer_snapshot = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "authz",
        "get-library-snapshot",
    )
    assert viewer_snapshot["current_user_role"] == "viewer"
    assert viewer_snapshot["can_manage_roles"] is False
    assert viewer_snapshot["roles"] == []
    assert viewer_snapshot["target_can_read"] is True
    assert viewer_snapshot["target_can_write"] is False

    denied_members = _cli_result(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "authz",
        "list-library-members",
    )
    assert denied_members.exit_code == 1
    assert "-> 403:" in denied_members.output

    denied_users = _cli_result(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "users",
        "list",
    )
    assert denied_users.exit_code == 1
    assert "-> 403:" in denied_users.output

    _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "alice",
        "authz",
        "revoke-library-member-role",
        "--user",
        viewer["username"],
        "--yes",
    )
    revoked_snapshot = _cli_json(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "authz",
        "get-library-snapshot",
    )
    assert revoked_snapshot["current_user_role"] is None
    assert revoked_snapshot["roles"] == []
    assert revoked_snapshot["target_can_read"] is False
    assert revoked_snapshot["target_can_write"] is False

    invalid_pair = _cli_result(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "pair",
        "device",
        "--code",
        "NOPE-0000",
        "--device-name",
        "Denied Device",
    )
    assert invalid_pair.exit_code == 1
    assert "-> 401:" in invalid_pair.output

    _cli_json(cli_multiuser_engine, "--as-user", "carol", "auth", "logout")
    logged_out = _cli_result(
        cli_multiuser_engine,
        "--as-user",
        "carol",
        "auth",
        "whoami",
    )
    assert logged_out.exit_code == 1
    assert "-> 401:" in logged_out.output
