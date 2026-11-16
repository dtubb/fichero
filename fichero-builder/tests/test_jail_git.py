"""dev-workflows.run.jail-home (H follow-up 2026-11-03): the scratch HOME of a jailed rung carries a .gitconfig that trusts the
owner-made check trees and names a committer, so a jailed `git rev-list --count` works (sharing bb1's ready rung failed on 'dubious ownership')."""
from __future__ import annotations

import subprocess

from fichero_builder import check_tool
from fichero_builder.check_tool import Config
from fichero_builder.jail import Jail


def test_a_jailed_rungs_scratch_home_trusts_every_tree_and_names_a_committer(tmp_path, monkeypatch):
    monkeypatch.setattr(check_tool, "_JAIL", Jail(user="u", workroot=str(tmp_path)))
    home = check_tool._env(tmp_path, Config())["HOME"]
    out = subprocess.run(["git", "config", "--file", f"{home}/.gitconfig", "--list"], capture_output=True, text=True).stdout
    assert "safe.directory=*" in out and "user.email=noreply@anthropic.com" in out


def test_an_unjailed_rung_gets_no_gitconfig(tmp_path, monkeypatch):
    monkeypatch.setattr(check_tool, "_JAIL", None)
    from pathlib import Path
    assert not (Path(check_tool._env(tmp_path, Config())["HOME"]) / ".gitconfig").exists()


def test_the_ready_script_names_the_git_error_when_it_cannot_count(tmp_path):
    """An unreadable repo is a FAIL line that names git's error, not 'commits ahead (cap 100)' with an empty count."""
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for a in (["config", "user.email", "a@b"], ["config", "user.name", "a"], ["commit", "-q", "--allow-empty", "-m", "x"], ["update-ref", "refs/remotes/origin/integration", "HEAD"]):
        subprocess.run(["git", "-C", str(repo), *a], check=True)
    script = next(p for p in __import__("pathlib").Path(__file__).resolve().parents if (p / "scripts" / "lane_ready_check.sh").exists()) / "scripts" / "lane_ready_check.sh"
    r = subprocess.run(["/bin/bash", str(script), "--no-guards", "deadbeefdeadbeef"], cwd=repo, capture_output=True, text=True)
    assert r.returncode != 0 and "FAIL: git could not" in r.stdout and "(cap" not in r.stdout, r.stdout + r.stderr
