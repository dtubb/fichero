"""`sharing.cli-pairs-a-device` (#5907): `fichero devices pair <link>` pairs the CLI as a revocable device.

WHY (owner 2026-10-20): no key copying. A CLI on another Mac reaches a host the way a phone does: it redeems the host's
pairing link, keeps the device token for that host, and the host can revoke it."""
from __future__ import annotations

import base64
import hashlib
import json
import stat

import httpx
import pytest
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import client as client_module
from fichero_cli import pairing
from fichero_cli.client import FicheroError

DER = b"the-hosts-public-key"
PIN = base64.b64encode(DER).decode()
TOKEN = "device-token-secret-value"
LOCAL = "https://mac-m4.local:8765"
TAILNET = "https://mac-m4.tail1234.ts.net"


def link(api_url=LOCAL, spki: str | None = PIN, code="ABC123") -> str:
    payload = {"v": 1, "api_url": api_url, "pair_code": code, "spki": spki, "library_path": "/x", "expires_at": "2099-01-01T00:00:00Z"}
    return "fichero://pair?payload=" + base64.b64encode(json.dumps(payload).encode()).decode()


class Host:
    """A fake host: records what /api/pair was sent and answers as scripted."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.sent = []

    def client(self, api_url, uds, spki):
        def handle(request: httpx.Request) -> httpx.Response:
            self.sent.append(json.loads(request.content))
            status, body = self.answers.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Client(base_url=api_url, transport=httpx.MockTransport(handle))


GOOD = (200, {"device_id": "dev-1", "device_token": TOKEN, "expires_at": "2099-01-01T00:00:00Z"})
PERSON = (401, {"detail": "person required: this library uses Multi-user, sign in as a person"})


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(pairing, "DEVICES_PATH", tmp_path / "paired-devices.json")
    for var in ("FICHERO_API_KEY", "FICHERO_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)


def run(monkeypatch, host, text, **kw):
    monkeypatch.setattr(pairing, "_open_client", host.client)
    kw.setdefault("fetch_der", lambda h, p: DER)
    return pairing.pair(text, device_name="bake-off (r1)", **kw)


def test_a_pinned_local_host_is_paired_and_its_token_is_stored_0600_and_reused(monkeypatch, tmp_path):
    host = Host([GOOD])
    done = run(monkeypatch, host, link())

    assert done == {"device_id": "dev-1", "name": "bake-off (r1)", "host": "mac-m4.local"}
    assert host.sent == [{"code": "ABC123", "device_name": "bake-off (r1)"}], "no username or password sent"
    assert stat.S_IMODE((tmp_path / "paired-devices.json").stat().st_mode) == 0o600
    key = client_module.engine_key(LOCAL, None)
    assert client_module._read_token(base_url=LOCAL, engine=key) == TOKEN
    assert client_module._read_token(base_url="https://other.local:8765",
                                     engine=client_module.engine_key("https://other.local:8765", None)) is None


def test_a_wrong_pin_is_refused_before_any_code_is_sent(monkeypatch):
    host = Host([GOOD])
    with pytest.raises(FicheroError, match="does not match the link's pin"):
        run(monkeypatch, host, link(), fetch_der=lambda h, p: b"someone-else")
    assert host.sent == []


def test_a_sha256_pin_is_accepted_too(monkeypatch):
    digest = "sha256/" + base64.b64encode(hashlib.sha256(DER).digest()).decode()
    assert run(monkeypatch, Host([GOOD]), link(spki=digest))["host"] == "mac-m4.local"


def test_http_is_refused_whatever_the_host(monkeypatch):
    host = Host([GOOD])
    with pytest.raises(FicheroError, match="plain http"):
        run(monkeypatch, host, link(api_url="http://mac-m4.local:8765"))
    with pytest.raises(FicheroError, match="plain http"):
        run(monkeypatch, host, link(api_url="http://x.tail1234.ts.net", spki=None))
    assert host.sent == []


def test_a_self_signed_host_with_no_pin_is_refused(monkeypatch):
    with pytest.raises(FicheroError, match="no certificate pin"):
        run(monkeypatch, Host([GOOD]), link(spki=None))


def test_a_ts_net_host_uses_system_trust_and_needs_no_pin(monkeypatch):
    def never(_h, _p):
        raise AssertionError("a .ts.net host's certificate is not pinned")
    done = run(monkeypatch, Host([GOOD]), link(api_url=TAILNET, spki=None), fetch_der=never)
    assert done["host"] == "mac-m4.tail1234.ts.net"
    assert pairing._read_store()[client_module.engine_key(TAILNET, None)]["spki"] is None


def test_person_required_asks_for_a_person_once_and_resends_with_it(monkeypatch):
    host = Host([PERSON, GOOD])
    run(monkeypatch, host, link(), ask_person=lambda: ("alice", "pw"))

    assert host.sent[0] == {"code": "ABC123", "device_name": "bake-off (r1)"}
    assert host.sent[1] == {"code": "ABC123", "device_name": "bake-off (r1)", "username": "alice", "password": "pw"}


def test_person_required_with_no_terminal_fails_in_words_and_stores_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(pairing.sys.stdin, "isatty", lambda: False, raising=False)
    host = Host([PERSON])
    with pytest.raises(FicheroError, match="no terminal to ask on"):
        run(monkeypatch, host, link())
    assert len(host.sent) == 1
    assert not (tmp_path / "paired-devices.json").exists()


def test_person_required_on_a_terminal_prompts_with_a_hidden_password(monkeypatch):
    monkeypatch.setattr(pairing.sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(pairing.sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    asked = []
    monkeypatch.setattr(pairing.getpass, "getpass", lambda prompt: asked.append(prompt) or "pw")
    host = Host([PERSON, GOOD])
    run(monkeypatch, host, link())

    assert asked == ["Password: "]
    assert host.sent[1]["username"] == "alice" and host.sent[1]["password"] == "pw"


def test_a_refused_code_says_so_and_stores_nothing(monkeypatch, tmp_path):
    with pytest.raises(FicheroError, match="invalid or expired pairing code"):
        run(monkeypatch, Host([(401, {"detail": "invalid or expired pairing code"})]), link())
    assert not (tmp_path / "paired-devices.json").exists()


def test_a_damaged_or_foreign_link_is_refused_in_words():
    for text in ("https://example.com/", "fichero://pair?payload=!!!", "fichero://pair"):
        with pytest.raises(FicheroError, match="pairing link"):
            pairing.parse_link(text)


def test_forget_drops_only_that_hosts_token(monkeypatch):
    run(monkeypatch, Host([GOOD]), link())
    run(monkeypatch, Host([GOOD]), link(api_url=TAILNET, spki=None))

    assert pairing.forget("mac-m4.local") == 1
    assert pairing.device_token(client_module.engine_key(LOCAL, None)) is None
    assert pairing.device_token(client_module.engine_key(TAILNET, None)) == TOKEN
    assert pairing.forget("nobody.local") == 0


def test_the_command_never_prints_the_token_and_reads_the_link_from_a_file(monkeypatch, tmp_path):
    monkeypatch.setattr(pairing, "_open_client", Host([GOOD]).client)
    monkeypatch.setattr(pairing, "served_spki_der", lambda h, p: DER)
    file = tmp_path / "link"
    file.write_text(link() + "\n")
    out = CliRunner(mix_stderr=False).invoke(cli.app, ["devices", "pair", "--link-file", str(file), "--name", "bake-off (r1)"])

    assert out.exit_code == 0, out.output
    assert TOKEN not in out.stdout + out.stderr
    assert "dev-1" in out.stdout
    assert pairing.device_token(client_module.engine_key(LOCAL, None)) == TOKEN


def test_the_command_needs_exactly_one_of_link_or_file():
    out = CliRunner(mix_stderr=False).invoke(cli.app, ["devices", "pair"])
    assert out.exit_code == 2


def test_a_signed_in_persons_session_beats_the_device_token(monkeypatch, tmp_path):
    """Review 583: actions by a signed-in person are theirs, not the device's."""
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    key = client_module.engine_key(LOCAL, None)
    run(monkeypatch, Host([GOOD]), link())
    assert client_module._read_token(base_url=LOCAL, engine=key) == TOKEN, "no session: the device speaks"
    cli._write_cli_session("alice-session", {"username": "alice"}, engine=key)
    assert client_module._read_token(base_url=LOCAL, engine=key) == "alice-session"


def test_the_owners_own_key_on_their_mac_beats_the_device_token_on_loopback(monkeypatch):
    local = "https://127.0.0.1:8765"
    key = client_module.engine_key(local, None)
    run(monkeypatch, Host([GOOD]), link(api_url=local, spki=PIN))
    monkeypatch.setenv("FICHERO_API_KEY", "owner-bootstrap")
    assert client_module._read_token(base_url=local, engine=key) == "owner-bootstrap"


def test_this_macs_owner_key_is_never_sent_to_a_remote_host_that_has_a_paired_device(monkeypatch):
    """Review 585: FICHERO_API_KEY is the owner's on THIS engine; the host's own device token is used instead."""
    key = client_module.engine_key(LOCAL, None)
    run(monkeypatch, Host([GOOD]), link())
    monkeypatch.setenv("FICHERO_API_KEY", "this-macs-owner-key")
    assert client_module._read_token(base_url=LOCAL, engine=key) == TOKEN


def test_a_link_on_argv_is_warned_about_without_echoing_it(monkeypatch):
    monkeypatch.setattr(pairing, "_open_client", Host([GOOD]).client)
    monkeypatch.setattr(pairing, "served_spki_der", lambda h, p: DER)
    text = link()
    out = CliRunner(mix_stderr=False).invoke(cli.app, ["devices", "pair", text])
    assert "shell history" in out.stderr and text not in out.stdout + out.stderr


def test_a_file_in_the_wrong_mode_does_not_wipe_other_engines_and_is_rewritten_0600(monkeypatch, tmp_path):
    run(monkeypatch, Host([GOOD]), link())
    path = tmp_path / "paired-devices.json"
    path.chmod(0o644)
    assert pairing.device_token(client_module.engine_key(LOCAL, None)) is None, "a loose file hands out nothing"
    run(monkeypatch, Host([GOOD]), link(api_url=TAILNET, spki=None))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert pairing.device_token(client_module.engine_key(LOCAL, None)) == TOKEN, "the first engine's entry survived"
    assert not (tmp_path / "paired-devices.json.tmp").exists()
