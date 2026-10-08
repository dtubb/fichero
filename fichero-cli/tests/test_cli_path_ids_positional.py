"""Every path parameter of a generated command is positional (#5584, `openapi.cli.path-ids-positional` in
`docs/contributor_manual/specs/harness/surfaces-from-openapi.md`).

An agent onboarding a project reported that `documents get-children` needs `doc_id` where other commands take
it positionally. The generator's rule is one rule for every command: a path parameter is a `typer.Argument`, a
body field or query parameter an option. These pin the rule on the whole generated surface and on the command
that was reported.
"""

from __future__ import annotations

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from fichero_cli import __main__ as cli_main

runner = CliRunner()


class _RecordingClient:
    """Stand-in for FicheroClient that records each request instead of making it."""

    calls: list[tuple[str, str, dict | None]] = []

    def __init__(self, **kwargs):
        self.base_url = kwargs.get("base_url") or "http://127.0.0.1:8765"

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def request(self, method, path, params=None, json=None, **_kw):
        type(self).calls.append((method, path, params))
        return {"items": []}

    def get_document(self, doc_id):  # `docs get` is hand-written over this client call
        return self.request("GET", f"/api/documents/{doc_id}")


@pytest.fixture
def recording_client(monkeypatch):
    _RecordingClient.calls = []
    monkeypatch.setattr(cli_main, "FicheroClient", _RecordingClient)
    return _RecordingClient


def test_openapi_cli_path_ids_positional__get_children_takes_the_id_as_get_does(recording_client):
    """openapi.cli.path-ids-positional: "every path parameter of a generated command is positional (`fichero
    docs get-children <doc_id>`, as `docs get <doc_id>`)\""""
    got = runner.invoke(cli_main.app, ["docs", "get", "doc-1"])
    children = runner.invoke(cli_main.app, ["docs", "get-children", "doc-1", "--limit", "5"])
    assert got.exit_code == 0, got.output
    assert children.exit_code == 0, children.output
    assert recording_client.calls[0][:2] == ("GET", "/api/documents/doc-1")
    method, path, params = recording_client.calls[1]
    assert (method, path) == ("GET", "/api/documents/doc-1/children") and params["limit"] == 5


def test_openapi_cli_path_ids_positional__every_path_parameter_is_an_argument():
    """openapi.cli.path-ids-positional: "... and every body field and query parameter an option." Checked on
    every generated command: a `{name}` in its route is a positional argument of the same name."""
    import re

    from click import Argument, Option

    root = get_command(cli_main.app)
    checked = 0
    for group in root.commands.values():
        for command in getattr(group, "commands", {}).values():
            match = re.search(r"\((GET|POST|PUT|PATCH|DELETE) (/api/\S+)\)", command.help or "")
            if not match:
                continue
            path_names = re.findall(r"{(\w+)(?::path)?}", match.group(2))
            arguments = [p.name for p in command.params if isinstance(p, Argument)]
            options = {p.name for p in command.params if isinstance(p, Option)}
            assert len(arguments) == len(path_names), (command.name, match.group(2), arguments)
            assert not set(arguments) & options
            checked += 1
    assert checked > 500, checked
