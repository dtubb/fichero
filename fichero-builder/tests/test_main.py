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
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "a" * 40 if rev == "HEAD" else "9" * 40)
    assert cli.main(["check", "--repo", "repo", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")]) == 0
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    rows = [r for r in journal.read() if r["event"] == "check"]
    assert rows and rows[0]["head"] == "a" * 40 and rows[0]["ok"] is True


def test_land_refuses_without_a_green_check_row_for_its_head(tmp_path, monkeypatch, capsys):
    import shutil

    shutil.copy(cli.Path(__file__).resolve().parents[2] / "harness.toml", tmp_path / "harness.toml")  # a rules file the gate accepts
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "b" * 40)
    # the log and verdicts in the test's own folder: the check tree, the cwd of a rung, is read-only to the worker (chunk A's red, 2026-11-01)
    args = ["land", "--repo", "repo", "HEAD", "--pinned", str(tmp_path), "--verdicts", str(tmp_path / "v"), "--log", str(tmp_path / "l"), "--state", str(tmp_path / "s")]
    assert cli.main(args) == 1 and "check" in capsys.readouterr().err
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    journal.append("check", head="b" * 40, ok=False)
    assert cli.main(args) == 1, "a red check does not count"


def test_check_resolves_the_head_before_the_ladder_runs(tmp_path, monkeypatch):
    """Review 1 M5: a commit made while the ladder runs must not get the green row."""
    shas = iter(["a" * 40, "b" * 40])
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: next(shas))
    seen = {}
    monkeypatch.setattr(cli.check_tool, "run_ladder", lambda repo, since, head, *a, **k: (seen.setdefault("head", head), {"ok": True, "failed": ""})[1])
    cli.main(["check", "--repo", "repo", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")])
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    row = [r for r in journal.read() if r["event"] == "check"][0]
    assert seen["head"] == "a" * 40 == row["head"], "the ladder judged the sha the row names"


def test_check_uses_the_pinned_rules_engine_repo_when_no_repo_is_given(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text('[check]\nengine_repo = "/engine"\n')
    seen = {}
    monkeypatch.setattr(cli.check_tool, "run_ladder", lambda repo, *a, **k: (seen.setdefault("repo", repo), {"ok": True, "failed": ""})[1])
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "c" * 40 if rev == "HEAD" else "9" * 40)
    assert cli.main(["check", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")]) == 0
    assert seen["repo"] == "/engine"
    (tmp_path / "harness.toml").write_text("[breif]\nx = 1\n")
    assert cli.main(["check", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")]) == 1, "a bad rules file refuses, no traceback"


def test_run_exits_zero_on_a_clean_done_and_one_on_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.run_mod, "real_procs", lambda home, wt: object())
    for end, code in (("done", 0), ("done-unsaid", 0), ("gone", 0), ("parked", 0), ("refused", 1)):
        monkeypatch.setattr(cli.run_mod, "run", lambda *a, **k: end)
        assert cli.main(["run", "--worktree", str(tmp_path), "--brief", str(tmp_path / "b"), "--root", str(tmp_path), "--state", str(tmp_path / "s"),
                         "--model", "sonnet"]) == code, end  # a rules file with no [models]: the model is named


def test_run_with_no_model_and_no_builder_role_refuses_as_a_question(tmp_path, monkeypatch, capsys):
    """dev-workflows.run.loop-roles: no model name is written in code; with no --model and no [models].builder, run refuses."""
    monkeypatch.setattr(cli.run_mod, "real_procs", lambda home, wt: object())
    monkeypatch.setattr(cli.run_mod, "run", lambda *a, **k: "done")
    assert cli.main(["run", "--worktree", str(tmp_path), "--brief", str(tmp_path / "b"), "--root", str(tmp_path), "--state", str(tmp_path / "s")]) == 1
    assert "[models].builder" in capsys.readouterr().err


def test_check_refuses_an_empty_range(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "resolve", lambda repo, rev: "d" * 40)
    monkeypatch.setattr(cli.check_tool, "run_ladder", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the ladder must not run")))
    assert cli.main(["check", "--repo", "r", "base", "HEAD", "--pinned", str(tmp_path), "--state", str(tmp_path / "s")]) == 1
    assert "empty" in capsys.readouterr().err


def test_check_passes_maintainer_through_to_the_ladder(monkeypatch, tmp_path, capsys):
    """`builder check --maintainer` reaches ladder_over as maintainer=True (the flag was parsed and dropped once)."""
    from fichero_builder import __main__ as m, check_tool

    seen = {}
    monkeypatch.setattr(m, "resolve", lambda repo, rev: {"a": "a" * 40, "b": "b" * 40}[rev])
    monkeypatch.setattr(check_tool, "ladder_over", lambda *a, **k: seen.update(k) or {"ok": True, "failed": "", "rungs": []})
    monkeypatch.setattr(m.journal, "append", lambda *a, **k: None)
    rules = tmp_path / "harness.toml"
    rules.write_text("[check]\nengine_repo = '" + str(tmp_path) + "'\n")
    assert m.main(["check", "a", "b", "--pinned", str(tmp_path), "--maintainer", "--state", str(tmp_path)]) == 0
    assert seen.get("maintainer") is True


@pytest.mark.parametrize("bad", ["a-directory", "missing-parent/land.log"])
def test_land_refuses_a_log_it_cannot_write_before_anything_with_a_row(tmp_path, monkeypatch, capsys, bad):
    """A directory as --log died with a traceback at the end of a six-minute ladder: the log is checked first."""
    (tmp_path / "a-directory").mkdir()
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    monkeypatch.setattr(cli.check_tool, "rules_problems", lambda p: pytest.fail("the log comes first"))
    rc = cli.main(["land", "--repo", "repo", "HEAD", "--pinned", str(tmp_path), "--verdicts", "v", "--log", str(tmp_path / bad), "--state", str(tmp_path / "s")])
    assert rc == 1 and "REFUSED (log)" in capsys.readouterr().err
    assert [r["refused"] for r in journal.read() if r["event"] == "land"] == ["log"]


def test_the_log_check_passes_a_new_file_and_an_owned_one_and_creates_nothing(tmp_path):
    from fichero_builder import land_tool

    assert land_tool.log_problem(tmp_path / "new.log") == "" and not (tmp_path / "new.log").exists()
    (tmp_path / "old.log").write_text("kept\n")
    assert land_tool.log_problem(tmp_path / "old.log") == "" and (tmp_path / "old.log").read_text() == "kept\n"
    (tmp_path / "link.log").symlink_to(tmp_path / "old.log")
    assert land_tool.log_problem(tmp_path / "link.log"), "the same refusal the append would give, now first"
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    assert land_tool.log_problem(shared / "new.log"), "a parent others can write: the append would refuse at the end of the work"


def test_the_hand_run_ladder_script_refuses_a_directory_log_before_its_ladder(tmp_path):
    import subprocess
    import sys

    script = cli.Path(__file__).resolve().parents[2] / "scripts" / "harness_land.py"
    r = subprocess.run([sys.executable, str(script), "repo", "HEAD", "--pinned", str(tmp_path), "--verdicts", "v", "--log", str(tmp_path)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode != 0 and "REFUSED (log)" in r.stderr and "Traceback" not in r.stderr


def subprocess_rev(repo, rev):
    import subprocess

    return subprocess.run(["git", "-C", str(repo), "rev-parse", rev], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path, monkeypatch):
    import subprocess

    for k, v in {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}.items():
        monkeypatch.setenv(k, v)
    e = tmp_path / "engine"
    e.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(e), *a], capture_output=True, text=True, check=True).stdout.strip()  # noqa: E731
    g("init", "-q", "-b", "integration"), (e / "f").write_text("0"), g("add", "f"), g("commit", "-qm", "base")
    g("checkout", "-qb", "lane"), (e / "g").write_text("1"), g("add", "g"), g("commit", "-qm", "mine")
    return e, g("rev-parse", "HEAD")


def test_land_refuses_a_green_row_that_does_not_cover_the_range(tmp_path, monkeypatch, capsys):
    """Review of range 1: `builder land` matched head and ok only; a row over head~1..head then landed the whole range."""
    e, head = _repo(tmp_path, monkeypatch)
    import re

    real = (cli.Path(__file__).resolve().parents[2] / "harness.toml").read_text()
    (tmp_path / "harness.toml").write_text(re.sub(r'^branch = .*$', 'branch = "integration"', real, flags=re.M))
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    journal.append("check", head=head, since=head, ok=True)
    args = ["land", "--repo", str(e), head, "--pinned", str(tmp_path), "--verdicts", str(tmp_path / "v"), "--log", str(tmp_path / "l"), "--state", str(tmp_path / "s")]
    assert cli.main(args) == 1 and "no green" in capsys.readouterr().err


def test_land_refuses_a_journal_others_can_write(tmp_path, monkeypatch, capsys):
    e, head = _repo(tmp_path, monkeypatch)
    import re

    real = (cli.Path(__file__).resolve().parents[2] / "harness.toml").read_text()
    (tmp_path / "harness.toml").write_text(re.sub(r'^branch = .*$', 'branch = "integration"', real, flags=re.M))
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    journal.append("check", head=head, ok=True)
    journal.path().chmod(0o666)
    args = ["land", "--repo", str(e), head, "--pinned", str(tmp_path), "--verdicts", str(tmp_path / "v"), "--log", str(tmp_path / "l"), "--state", str(tmp_path / "s")]
    assert cli.main(args) == 1 and "REFUSED (journal)" in capsys.readouterr().err


def test_land_with_a_green_check_row_runs_the_verdict_and_boundary_only_never_the_ladder_again(tmp_path, monkeypatch, capsys):
    """Item 9 (2026-11-01): the row is the ladder's result for this exact head; a second ladder doubled the pytest load."""
    from fichero_builder import check_tool, land_tool

    e, head = _repo(tmp_path, monkeypatch)
    import re

    real = (cli.Path(__file__).resolve().parents[2] / "harness.toml").read_text()  # a rules file the gate accepts, its boundary kept
    (tmp_path / "harness.toml").write_text(re.sub(r'^branch = .*$', 'branch = "integration"', real, flags=re.M))
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    base = subprocess_rev(e, "integration")
    journal.append("check", head=head, since=base, ok=True)
    monkeypatch.setattr(check_tool, "run_ladder", lambda *a, **k: pytest.fail("the ladder ran again"))
    args = ["land", "--repo", str(e), head, "--pinned", str(tmp_path), "--verdicts", str(tmp_path / "v"), "--log", str(tmp_path / "l"), "--state", str(tmp_path / "s")]
    assert cli.main(args) == 1 and "verdict" in (tmp_path / "l").read_text()  # no READY verdict yet
    land_tool.write_verdict(tmp_path / "v", e, "integration", head)
    assert cli.main(args) == 0
    assert f"READY TO LAND: git push origin {head}:refs/heads/integration" in capsys.readouterr().out
    (e / "h").write_text("sk-" + "ant-abcdef12345"), monkeypatch.chdir(e)  # built here: the boundary scans this file's own added lines too
    import subprocess
    subprocess.run(["git", "-C", str(e), "add", "h"], check=True), subprocess.run(["git", "-C", str(e), "commit", "-qm", "leak"], check=True)
    head2 = subprocess.run(["git", "-C", str(e), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    journal.append("check", head=head2, since=base, ok=True), land_tool.write_verdict(tmp_path / "v", e, "integration", head2)
    args[3] = head2
    assert cli.main(args) == 1 and "boundary" in (tmp_path / "l").read_text().splitlines()[-1]


def test_the_rules_checks_accept_the_settings_later_commits_add_and_still_refuse_a_misspelt_one(tmp_path):
    """The check overlays the batch tip's harness.toml on each piece's code, so a piece must not refuse settings it does not read yet."""
    from fichero_builder import check_tool, jail

    base = '[jail]\nuser = "w"\nworkroot = "/w"\ncode_map = "~/x"\n[land]\nbranch = "b"\nboundary = ["x"]\npinned_dir = "/p"\n[queue]\nworkers = 1\n[triage.labels]\na = "b"\n'
    (tmp_path / "harness.toml").write_text(base)
    assert check_tool.load(tmp_path) and jail.load(tmp_path).user == "w"
    assert not [p for p in check_tool.rules_problems(tmp_path) if "unknown" in p]
    (tmp_path / "harness.toml").write_text(base + "[queuee]\nx = 1\n")
    with pytest.raises(ValueError, match="unknown tables"):
        check_tool.load(tmp_path)
    (tmp_path / "harness.toml").write_text(base.replace("code_map", "code_mapp"))
    with pytest.raises(ValueError, match="unknown keys"):
        jail.load(tmp_path)


def test_a_land_branch_that_does_not_resolve_is_a_row_in_the_log(tmp_path, monkeypatch, capsys):
    """Every refusal of the gate is a row, and this one was not."""
    from fichero_builder import land_tool

    e, head = _repo(tmp_path, monkeypatch)
    import re

    real = (cli.Path(__file__).resolve().parents[2] / "harness.toml").read_text()
    (tmp_path / "harness.toml").write_text(re.sub(r'^branch = .*$', 'branch = "no-such-branch"', real, flags=re.M))
    ok, out = land_tool.gate(str(e), head, tmp_path, tmp_path / "v", tmp_path / "l")
    assert not ok and "REFUSED" in out and "no-such-branch" in (tmp_path / "l").read_text()
