"""A generated flag says what it takes, a list flag takes a list three ways, and a generated command
has a readable name (#5501; `openapi.cli.flags-say-what-they-take` and `openapi.cli.names-from-the-handler`
in `docs/contributor_manual/specs/harness/surfaces-from-openapi.md`)."""

from __future__ import annotations

import collections
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from fichero_cli import __main__ as cli_main

runner = CliRunner()


class _RecordingClient:
    calls: list[tuple[str, str, dict | None, object]] = []

    def __init__(self, **kwargs):
        self.base_url = kwargs.get("base_url") or "http://127.0.0.1:8765"

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def request(self, method, path, params=None, json=None, **_kw):
        type(self).calls.append((method, path, params, json))
        return {"ok": True}


@pytest.fixture
def recording_client(monkeypatch):
    _RecordingClient.calls = []
    monkeypatch.setattr(cli_main, "FicheroClient", _RecordingClient)
    return _RecordingClient


def _help(*args: str) -> str:
    result = runner.invoke(cli_main.app, [*args, "--help"], env={"COLUMNS": "400"})
    assert result.exit_code == 0, result.output
    return " ".join(result.output.split())


def test_openapi_cli_flags_say_what_they_take__help_is_the_fields_description():
    """openapi.cli.flags-say-what-they-take: "a generated flag's `--help` is the field's description from the
    contract ... never only `Request field: X`\""""
    text = _help("recipes", "assemble")
    assert "Request field:" not in text
    assert "BCP 47 language tags" in text
    assert "repeat the flag" in text  # --languages is a list
    setup = _help("recipes", "save-project-setup")
    assert "directions as {script: direction}" in setup and "JSON." in setup


def test_openapi_cli_flags_say_what_they_take__no_generated_flag_says_only_request_field():
    """openapi.cli.flags-say-what-they-take: the rule holds on every generated command."""
    source = (Path(cli_main.__file__).parent / "openapi_surface_generated.py").read_text()
    assert "Request field:" not in source


@pytest.mark.parametrize(
    "given",
    [
        ["--languages", "es", "--languages", "la"],
        ["--languages", "es,la"],
        ["--languages", '["es", "la"]'],
    ],
    ids=["repeated", "comma-separated", "json"],
)
def test_openapi_cli_flags_say_what_they_take__a_list_three_ways(recording_client, given):
    """openapi.cli.flags-say-what-they-take: "A list of plain values ... is given by repeating the flag, as
    one comma-separated value, or as a JSON list\""""
    result = runner.invoke(cli_main.app, ["recipes", "assemble", *given, "--scripts", "Latn"])
    assert result.exit_code == 0, result.output
    method, path, _params, body = recording_client.calls[-1]
    assert (method, path) == ("POST", "/api/recipes/assemble")
    assert body["languages"] == ["es", "la"]
    assert body["scripts"] == ["Latn"]


def test_openapi_cli_flags_say_what_they_take__a_bad_json_list_is_refused(recording_client):
    """Edge: a value that starts as a JSON list but is not one is refused in words, never sent split."""
    result = runner.invoke(cli_main.app, ["recipes", "assemble", "--languages", '["es"', "--scripts", "Latn"])
    assert result.exit_code != 0
    assert "Invalid JSON list" in result.output
    assert recording_client.calls == []


def test_openapi_cli_flags_say_what_they_take__a_list_query_parameter_splits_too(recording_client):
    """Edge: a list query parameter takes the same three forms."""
    result = runner.invoke(cli_main.app, ["citations", "export-bibtex", "--document-ids", "a,b"])
    assert result.exit_code == 0, result.output
    _method, path, params, _body = recording_client.calls[-1]
    assert path == "/api/citations/export" and params["document_ids"] == ["a", "b"]


def _group(*names: str):
    command = get_command(cli_main.app)
    for name in names:
        command = command.commands[name]
    return command


@pytest.mark.parametrize(
    ("group", "name", "old"),
    [
        ("sync-folders", "tie", "tie-the-project-to-a-on-the-engine-s-disk"),
        ("sync-folders", "put-mode", "keep-a-synced-as-index-or-keep-arranged"),
        ("evaluation", "start", "score-trained-and-out-of-the-box-models-on-the-held-out-checked-pages-as-one-job"),
    ],
)
def test_openapi_cli_names_from_the_handler__readable_name_old_name_hidden(group, name, old):
    """openapi.cli.names-from-the-handler: "named ... by the route handler's name less the words its group
    already says ... The name it had before runs still, hidden\""""
    commands = _group(group).commands
    assert name in commands and not commands[name].hidden
    assert old in commands and commands[old].hidden
    assert commands[old].callback.__name__ == commands[name].callback.__name__  # one function, two names


def test_openapi_cli_names_from_the_handler__no_group_registers_a_name_twice():
    """openapi.cli.names-from-the-handler: "A generated command never takes the name of a hand-written one in
    the same group" -- typer would keep only the last of the two."""

    def walk(app, prefix, out):
        counts = collections.Counter(c.name or c.callback.__name__.replace("_", "-") for c in app.registered_commands)
        out.extend(f"{prefix} {n}" for n, k in counts.items() if k > 1)
        for group in app.registered_groups:
            walk(group.typer_instance, f"{prefix} {group.name}", out)
        return out

    assert walk(cli_main.app, "", []) == []


def test_openapi_cli_names_from_the_handler__hand_written_command_still_answers():
    """Edge: `docs inspector` is hand-written; the generated inspector route took another name, not this one."""
    commands = _group("docs").commands
    assert commands["inspector"].callback.__module__ == "fichero_cli.__main__"
