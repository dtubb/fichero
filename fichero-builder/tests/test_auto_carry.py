"""dev-workflows.run.auto-rules, more classes (owner via the manager 2026-11-03): an approve carries to a head whose named files have
the same diff, and the day's auto decisions are one list for the manager's audit."""
from __future__ import annotations

import subprocess

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, queue

AUTO = ("approval-carry-same-file-diffs",)


def _g(repo, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    r = tmp_path / "r"
    r.mkdir()
    _g(r, "init", "-q", "-b", "integration")
    (r / "t_test.py").write_text("def test_a():\n    assert 1\n    assert 2\n")
    (r / "src.py").write_text("x = 1\n")
    _g(r, "add", "."), _g(r, "commit", "-qm", "base")
    _g(r, "checkout", "-q", "-b", "lane")
    (r / "t_test.py").write_text("def test_a():\n    assert 1\n")
    _g(r, "commit", "-qam", "trim the test")
    return r


def _step(head, approved, **flags):
    return {"head": head, "approved_head": approved, "approved_tests": ["t_test.py"], **flags}


def test_an_approve_carries_to_added_commits_and_to_a_rebase_with_the_same_file_diff_and_never_otherwise(repo):
    h1 = _g(repo, "rev-parse", "HEAD")
    (repo / "src.py").write_text("x = 2\n")
    _g(repo, "commit", "-qam", "an added commit elsewhere")
    h2 = _g(repo, "rev-parse", "HEAD")
    s = _step(h2, h1, approve_red=True)
    assert queue.carry_approvals(s, str(repo), "integration", AUTO) and s["approved_head"] == h2 and queue._approved(s, "approve_red")
    _g(repo, "checkout", "-q", "integration")
    (repo / "other.py").write_text("y = 1\n")
    _g(repo, "add", "."), _g(repo, "commit", "-qm", "the base moved")
    _g(repo, "checkout", "-q", "lane"), _g(repo, "rebase", "-q", "integration")
    h3 = _g(repo, "rev-parse", "HEAD")
    assert queue.carry_approvals(_step(h3, h1, approve_weakened=True), str(repo), "integration", AUTO), "a rebase: the named file's range-diff is empty"
    (repo / "t_test.py").write_text("def test_a():\n    pass\n")
    _g(repo, "commit", "-qam", "the named file changed again")
    h4 = _g(repo, "rev-parse", "HEAD")
    assert not queue.carry_approvals(_step(h4, h1, approve_red=True), str(repo), "integration", AUTO), "a changed named file never carries"
    assert not queue.carry_approvals(_step(h2, h1, approve_red=True, maintainer=True), str(repo), "integration", AUTO), "a maintainer approve never carries"
    assert not queue.carry_approvals({**_step(h2, h1, approve_red=True), "approved_tests": []}, str(repo), "integration", AUTO), "no named file: no carry"
    assert not queue.carry_approvals(_step(h2, h1, approve_red=True), str(repo), "integration", ()), "off unless named"
    assert [r["rule"] for r in journal.read() if r["event"] == "auto"] == ["approval-carry-same-file-diffs"] * 2


def test_the_days_auto_decisions_are_one_list_by_rule(repo, capsys):
    journal.append("auto", rule="red-on-base-trim-only", head="a" * 40, file="t_test.py", detail="adds no check")
    journal.append("auto", rule="approval-carry-same-file-diffs", head="b" * 40, file="t_test.py", detail="the same diff")
    assert cli.main(["auto", "--state", str(journal.STATE)]) == 0
    out = capsys.readouterr().out
    assert "2 auto decision(s)" in out and "red-on-base-trim-only: 1" in out and "approval-carry-same-file-diffs: 1" in out and "bbbbbbbbb t_test.py" in out


def test_builder_auto_lists_the_spec_ok_proposals_no_batch_has_folded_in(repo, capsys):
    spec = repo / "docs" / "s.md"
    spec.parent.mkdir()
    spec.write_text("- `a.one` [GAP] — x\n- `a.two` [OK] — y\n")
    journal.append("spec-ok-proposed", lane="lane-x", sha="c" * 40, file="docs/s.md", id="a.one", tests=["t.py"])
    journal.append("spec-ok-proposed", lane="lane-x", sha="c" * 40, file="docs/s.md", id="a.two", tests=[])
    assert cli.main(["auto", "--state", str(journal.STATE), "--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "spec-ok proposals not folded yet (any day): 1" in out and "lane-x ccccccccc docs/s.md: `a.one` [OK] Tests: t.py" in out


def test_an_older_approve_that_does_not_carry_says_why_in_a_row(repo):
    h1 = _g(repo, "rev-parse", "HEAD")
    (repo / "t_test.py").write_text("def test_a():\n    pass\n")
    _g(repo, "commit", "-qam", "the named file changed")
    h2 = _g(repo, "rev-parse", "HEAD")
    assert not queue.carry_approvals(_step(h2, h1, approve_red=True), str(repo), "integration", AUTO)
    assert not queue.carry_approvals(_step(h2, h1, approve_red=True), str(repo), "integration", ())
    rows = [r["detail"] for r in journal.read() if r["event"] == "carry-declined"]
    assert rows == ["t_test.py: its diff changed", "the rule is not in [check].auto"]
    assert not queue.carry_approvals(_step(h2, h2, approve_red=True), str(repo), "integration", AUTO), "same head: nothing to carry, no row"
    assert len([r for r in journal.read() if r["event"] == "carry-declined"]) == 2
