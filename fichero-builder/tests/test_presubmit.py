"""dev-workflows.run.presubmit (speed batch 2, manager 2026-11-03): `builder done` runs the lane's ready check with its guards in
the lane's tree first, so a guard's red stops in the lane instead of costing a ladder."""
from __future__ import annotations

import subprocess

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def lane(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    wt = tmp_path / "wt"
    (wt / "scripts").mkdir(parents=True)
    (wt / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\n[ -e RED ] && { echo 'FAIL: scripts/check_spec_build_order_shape.py'; exit 1; }\necho READY\n")
    (wt / "harness.toml").write_text('[check]\nready = ["scripts/lane_ready_check.sh", "--no-guards", "HEAD"]\n')
    _git(wt, "init", "-q", "-b", "main")
    _git(wt, "add", "."), _git(wt, "commit", "-qm", "base")
    queue.add("ext", str(wt), "1.1", str(tmp_path / "b"), [7], kind="external")
    return wt


def test_a_red_presubmit_refuses_the_done_and_a_green_one_lets_it_through(lane, capsys):
    (lane / "RED").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "red")
    sha = _git(lane, "rev-parse", "HEAD")
    assert cli.main(["done", "ext", sha, "--state", str(journal.STATE)]) == 1
    out = capsys.readouterr().out
    assert "REFUSED: the presubmit" in out and "check_spec_build_order_shape" in out
    assert queue.load()[0]["steps"][0]["state"] == "queued", "nothing went to the ladder"
    _git(lane, "rm", "-q", "RED"), _git(lane, "commit", "-qm", "fixed")
    assert cli.main(["done", "ext", _git(lane, "rev-parse", "HEAD"), "--state", str(journal.STATE)]) == 0
    assert [r["state"] for r in journal.read() if r["event"] == "presubmit"] == ["red", "green"]


def test_a_tree_not_at_the_sha_or_dirty_is_skipped_and_said_and_no_presubmit_skips_on_purpose(lane, capsys):
    (lane / "RED").write_text("x")
    _git(lane, "add", "."), _git(lane, "commit", "-qm", "red")
    red = _git(lane, "rev-parse", "HEAD")
    _git(lane, "checkout", "-q", "HEAD~1")
    ok, said = queue.presubmit("ext", red)
    assert ok and said.startswith("presubmit skipped") and "not at" in said, "the guards read the tree, so a tree at another sha is not judged"
    _git(lane, "checkout", "-q", red)
    (lane / "scripts" / "lane_ready_check.sh").write_text("#!/bin/bash\nexit 0\n")  # a dirty tracked file
    assert queue.presubmit("ext", red)[1].startswith("presubmit skipped") and "dirty" in queue.presubmit("ext", red)[1]
    _git(lane, "checkout", "-q", "--", ".")
    assert cli.main(["done", "ext", red, "--no-presubmit", "--state", str(journal.STATE)]) == 0, "the manager's skip"
