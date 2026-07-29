"""Argument parsing and subcommand dispatch for `python -m fichero_cli` (#4227).

These exercise the Typer app object in-process (no subprocess, no live server):
which command groups are registered, that an unknown command fails loudly, and
that the shared `@app.callback()` options actually reach the client the invoked
command builds. The existing subprocess `--help` smoke test in
`fichero-server/tests/unit/cli/test_cli_entrypoint.py` proves the module
imports; this file proves the parse → dispatch → client wiring.
"""

from __future__ import annotations

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from fichero_cli import __main__ as cli_main

runner = CliRunner()

# Groups every documented workflow in docs/contributor/cli-test-harness.md and
# AGENTS.md's "reproduce against the CLI first" rule depends on. A rename that
# drops one of these breaks the harness silently.
REQUIRED_COMMANDS = (
    "auth",
    "artifacts",
    "claim",
    "compare",
    "devices",
    "docs",
    "engine",
    "entity",
    "health",
    "import",
    "kg",
    "library",
    "notes",
    "pair",
    "providers",
    "search",
    "settings",
    "users",
    "workflow",
)


def _registered_command_names() -> set[str]:
    return set(get_command(cli_main.app).commands)


class _RecordingClient:
    """Stand-in for FicheroClient that records its constructor kwargs."""

    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = dict(kwargs)
        self.base_url = kwargs.get("base_url") or "http://127.0.0.1:8765"
        self.token = kwargs.get("token")
        self.library_path = kwargs.get("library_path")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def health(self):
        return {"status": "ok"}


@pytest.fixture
def recording_client(monkeypatch):
    _RecordingClient.last_kwargs = None
    monkeypatch.setattr(cli_main, "FicheroClient", _RecordingClient)
    return _RecordingClient


@pytest.mark.parametrize("name", REQUIRED_COMMANDS)
def test_required_command_is_registered(name):
    assert name in _registered_command_names()


def test_command_names_are_unique_and_nonempty():
    names = list(get_command(cli_main.app).commands)
    assert len(names) == len(set(names))
    assert all(name and not name.startswith("-") for name in names)


def test_bare_invocation_shows_help_and_does_not_dial_the_server(recording_client):
    result = runner.invoke(cli_main.app, [])

    # no_args_is_help=True: exit code is Click's "no command" code, not 0.
    assert result.exit_code != 0
    assert "Usage:" in result.output
    assert recording_client.last_kwargs is None


def test_unknown_command_fails_loudly(recording_client):
    result = runner.invoke(cli_main.app, ["definitely-not-a-command"])

    assert result.exit_code == 2
    assert "No such command" in result.output
    assert recording_client.last_kwargs is None


def test_unknown_subcommand_of_a_group_fails_loudly(recording_client):
    result = runner.invoke(cli_main.app, ["docs", "not-a-docs-subcommand"])

    assert result.exit_code == 2
    assert recording_client.last_kwargs is None


def test_global_options_reach_the_client(recording_client, tmp_path):
    library = tmp_path / "Library.fichero"
    result = runner.invoke(
        cli_main.app,
        [
            "--base-url",
            "https://remote.example:8765",
            "--token",
            "flag-token",
            "--library",
            str(library),
            "health",
        ],
    )

    assert result.exit_code == 0, result.output
    assert recording_client.last_kwargs == {
        "base_url": "https://remote.example:8765",
        "token": "flag-token",
        "library_path": str(library),
    }


def test_as_user_is_forwarded_only_when_given(recording_client):
    assert runner.invoke(cli_main.app, ["health"]).exit_code == 0
    assert "as_user" not in recording_client.last_kwargs

    assert runner.invoke(cli_main.app, ["--as-user", "agent", "health"]).exit_code == 0
    assert recording_client.last_kwargs["as_user"] == "agent"


def test_blank_as_user_is_not_forwarded(recording_client):
    result = runner.invoke(cli_main.app, ["--as-user", "   ", "health"])

    assert result.exit_code == 0, result.output
    assert "as_user" not in recording_client.last_kwargs


def test_json_flag_switches_rendering(recording_client):
    human = runner.invoke(cli_main.app, ["health"])
    as_json = runner.invoke(cli_main.app, ["--json", "health"])

    assert human.exit_code == 0 and as_json.exit_code == 0
    assert '"status": "ok"' in as_json.output
    assert as_json.output != human.output
