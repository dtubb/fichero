"""dev-workflows.tool.check and dev-workflows.run.review-and-land: `builder check` leaves a journal row, `builder land`
refuses without a green one for its head, and the journal defaults to the jail's workroot so the owner reads it without sudo."""
from __future__ import annotations

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "default")
    monkeypatch.delenv("FICHERO_BUILDER_STATE", raising=False)


def test_the_journal_defaults_to_the_workroots_state_dir(tmp_path):
    (tmp_path / "harness.toml").write_text('[jail]\nworkroot = "/w"\n')
    assert cli.state_dir(tmp_path, None) == journal.Path("/w/state")
    assert cli.state_dir(tmp_path, "/x") == journal.Path("/x"), "--state wins"
    (tmp_path / "harness.toml").write_text("[check]\n")
    assert cli.state_dir(tmp_path, None) == tmp_path / "default", "no workroot: the default"


def test_check_writes_a_row_with_the_heads_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.check_tool, "run_ladder", lambda *a, **k: {"ok": True, "failed": ""})
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "a" * 40)
    assert cli.main(["check", "repo", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")]) == 0
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    rows = [r for r in journal.read() if r["event"] == "check"]
    assert rows and rows[0]["head"] == "a" * 40 and rows[0]["ok"] is True


def test_land_refuses_without_a_green_check_row_for_its_head(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "b" * 40)
    args = ["land", "repo", "HEAD", "--pinned", str(tmp_path), "--verdicts", "v", "--log", "l", "--state", str(tmp_path / "s")]
    assert cli.main(args) == 1 and "check" in capsys.readouterr().err
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    journal.append("check", head="b" * 40, ok=False)
    assert cli.main(args) == 1, "a red check does not count"
