"""`kg dedupe-entities` / `kg dedupe-claims` wiring (#4508).

The verbs are thin: dry-run by default, ``--apply`` opts into execution, and
each maps 1:1 onto one dedupe endpoint. These tests prove the parse →
dispatch → client-method wiring in-process (no live server), mirroring
test_cli_dispatch.py.
"""

from __future__ import annotations

from typer.main import get_command
from typer.testing import CliRunner

from fichero_cli import __main__ as cli_main

runner = CliRunner()


def _kg_commands() -> set[str]:
    kg = get_command(cli_main.app).commands["kg"]
    return set(kg.commands)


def test_dedupe_commands_registered():
    assert {"dedupe-entities", "dedupe-claims"} <= _kg_commands()


class _RecordingDedupeClient:
    """Records the dedupe call the command dispatches."""

    calls: list[tuple[str, dict]] = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def dedupe_entities(self, **kwargs):
        type(self).calls.append(("dedupe_entities", kwargs))
        return {"dry_run": not kwargs["apply"], "groups": []}

    def dedupe_claims(self, **kwargs):
        type(self).calls.append(("dedupe_claims", kwargs))
        return {"dry_run": not kwargs["apply"], "groups": []}


def test_dedupe_entities_defaults_to_dry_run(monkeypatch):
    _RecordingDedupeClient.calls = []
    monkeypatch.setattr(cli_main, "FicheroClient", _RecordingDedupeClient)
    result = runner.invoke(cli_main.app, ["kg", "dedupe-entities"])
    assert result.exit_code == 0, result.output
    assert _RecordingDedupeClient.calls == [
        (
            "dedupe_entities",
            {"apply": False, "include_reviewed": False, "min_similarity": None},
        )
    ]


def test_dedupe_claims_apply_and_threshold(monkeypatch):
    _RecordingDedupeClient.calls = []
    monkeypatch.setattr(cli_main, "FicheroClient", _RecordingDedupeClient)
    result = runner.invoke(
        cli_main.app,
        ["kg", "dedupe-claims", "--apply", "--near-duplicate-threshold", "0.9"],
    )
    assert result.exit_code == 0, result.output
    assert _RecordingDedupeClient.calls == [
        (
            "dedupe_claims",
            {
                "apply": True,
                "include_reviewed": False,
                "near_duplicate_threshold": 0.9,
            },
        )
    ]
