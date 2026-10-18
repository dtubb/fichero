"""`sharing.cli-session-per-engine` (#5757): the CLI keeps a session per engine it dials.

WHY (tester's R1 re-run, 2026-10-17): the CLI stored ONE session and sent its token to every engine. After signing in as
alice on engine A, a fresh engine on another socket answered 401 `bootstrap_mismatch` to every CLI call, because alice's
token from A shadowed that engine's own credential. A session is keyed by the engine it was made on (its socket or
URL); a session made on another engine is never sent here."""
from __future__ import annotations

import json
import stat

from fichero_cli import __main__ as cli
from fichero_cli import client as client_module

ENGINE_A = "https://engine-a.example:8765"
ENGINE_B = "https://engine-b.example:8765"


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def test_a_session_made_on_one_engine_is_not_sent_to_another(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    cli._write_cli_session("alice-on-a", {"username": "alice"}, engine=client_module.engine_key(ENGINE_A, None))
    monkeypatch.setenv("FICHERO_API_KEY", "engine-b-bootstrap")

    assert client_module._read_token(base_url=ENGINE_A, engine=client_module.engine_key(ENGINE_A, None)) == "alice-on-a"
    assert client_module._read_token(base_url=ENGINE_B, engine=client_module.engine_key(ENGINE_B, None)) == "engine-b-bootstrap"


def test_an_explicit_account_with_no_session_on_this_engine_gets_no_token(monkeypatch, tmp_path):
    """`--as alice` must never fall back to another engine's token (nor to the bootstrap token: that would act as
    the owner)."""
    _isolate(monkeypatch, tmp_path)
    cli._write_cli_session("alice-on-a", {"username": "alice"}, engine=client_module.engine_key(ENGINE_A, None))

    assert client_module._read_token(base_url=ENGINE_A, as_user="alice",
                                     engine=client_module.engine_key(ENGINE_A, None)) == "alice-on-a"
    assert client_module._read_token(base_url=ENGINE_B, as_user="alice",
                                     engine=client_module.engine_key(ENGINE_B, None)) is None


def test_each_engine_keeps_its_own_session_for_the_same_person(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    key_a, key_b = client_module.engine_key(ENGINE_A, None), client_module.engine_key(ENGINE_B, None)
    cli._write_cli_session("alice-on-a", {"username": "alice"}, engine=key_a)
    cli._write_cli_session("alice-on-b", {"username": "alice"}, engine=key_b)

    assert client_module._read_token(base_url=ENGINE_A, as_user="alice", engine=key_a) == "alice-on-a"
    assert client_module._read_token(base_url=ENGINE_B, as_user="alice", engine=key_b) == "alice-on-b"
    mode = stat.S_IMODE((tmp_path / "cli-session.json").stat().st_mode)
    assert mode == 0o600, "the session file holds tokens: owner-only"
    json.loads((tmp_path / "cli-session.json").read_text())  # still one valid file


def test_a_session_file_written_before_this_has_no_engine_and_still_works_anywhere(monkeypatch, tmp_path):
    """Existing files carry no engine; they keep working until the next login stamps one."""
    _isolate(monkeypatch, tmp_path)
    (tmp_path / "cli-session.json").write_text(json.dumps({"current_user": "alice", "sessions": {
        "alice": {"session_token": "legacy", "user": {"username": "alice"}}}}))
    (tmp_path / "cli-session.json").chmod(0o600)
    assert client_module._read_token(base_url=ENGINE_B, as_user="alice", engine=client_module.engine_key(ENGINE_B, None)) == "legacy"


def test_a_legacy_session_an_engine_refuses_is_dropped_not_tried_elsewhere(monkeypatch, tmp_path):
    """review 76: a session saved before sessions were keyed by engine carries no engine, so any engine was offered it.
    The first engine that answers 401 to it drops it from the file; it is never sent to another."""
    import httpx

    _isolate(monkeypatch, tmp_path)
    path = client_module._CLI_SESSION_PATH
    path.write_text(json.dumps({"current_user": "alice", "sessions": {"alice": {"session_token": "old-token"}}}))
    path.chmod(0o600)
    monkeypatch.setenv("FICHERO_API_KEY", "bootstrap")

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(401, json={"detail": "bad token"})

    c = client_module.FicheroClient(base_url=ENGINE_A, transport=httpx.MockTransport(handler))
    try:
        c.request("GET", "/api/health")
    except client_module.FicheroError:
        pass  # the 401 is the point

    assert json.loads(path.read_text())["sessions"] == {}
    assert client_module._read_token(base_url=ENGINE_B, as_user="alice",
                                     engine=client_module.engine_key(ENGINE_B, None)) is None
