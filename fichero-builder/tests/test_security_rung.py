"""The `security` rung: each scanner's new findings red it, a baselined one does not, a missing scanner refuses; the thresholds and
the waivers (#6600, Step 2.30). The scanners' JSON outputs are the fixtures: no scanner binary runs here."""
import datetime as dt
import json
import subprocess

import pytest

from fichero_builder import check_tool, journal
from fichero_builder import security_rung as sr

B602 = {"filename": "scripts/conv.py", "line_number": 3, "test_id": "B602", "issue_severity": "HIGH", "issue_confidence": "HIGH",
        "issue_text": "subprocess call with shell=True", "code": "subprocess.run(x, shell=True)"}


def test_each_scanner_s_new_findings_red_the_rung_a_baselined_one_does_not_and_a_missing_scanner_refuses():
    rows = sr.read_bandit({"results": [B602]})
    assert rows[0]["red"] and rows[0]["where"] == "scripts/conv.py:3" and rows[0]["rule"] == "B602"
    assert sr.read_bandit({"results": [B602]}, baseline={"results": [B602]}) == []  # the same finding in the baseline: green
    sg = {"results": [{"check_id": "swift.process-shell", "path": "fichero/A.swift", "start": {"line": 9}, "extra": {"severity": "ERROR", "message": "m"}}]}
    assert sr.read_semgrep(sg)[0]["red"]
    osv = {"results": [{"packages": [{"package": {"name": "pillow", "version": "10.0"}, "groups": [{"ids": ["GHSA-1"], "max_severity": "8.0"}],
                                      "vulnerabilities": [{"id": "GHSA-1", "aliases": ["CVE-2024-1"]}]}]}]}
    r = sr.read_osv(osv)[0]
    assert r["red"] and "pillow" in r["where"] and r["rule"] == "GHSA-1" and "CVSS 8" in r["severity"]
    leak = [{"RuleID": "generic-api-key", "File": "a.py", "StartLine": 4, "Secret": "sk-live-abc", "Fingerprint": "f1"}]
    row = sr.read_gitleaks(leak)[0]
    assert row["red"] and row["detail"] == "REDACTED" and "sk-live-abc" not in sr.table([row]) and "sk-live-abc" not in str(row)
    assert sr.read_gitleaks(leak, baseline=leak) == []
    # a runner without semgrep prints REFUSED naming it; an unpinned or other-version tool is refused too
    pins = {"bandit": "1.8.6", "semgrep": "1.0", "gitleaks": "8.0", "osv-scanner-enabled": False}
    out = sr.refused_tools({"bandit": "1.8.6", "semgrep": None, "gitleaks": "8.0"}, pins)
    assert out == ["REFUSED: semgrep is not installed on the runner"]
    assert "pin is 1.0" in sr.refused_tools({"bandit": "1.8.6", "semgrep": "1.1", "gitleaks": "8.0"}, pins)[0]
    assert "no pinned version" in sr.refused_tools({"bandit": "1", "semgrep": "1", "gitleaks": "1"}, {"bandit": "1", "semgrep": "1", "osv-scanner-enabled": False})[0]
    assert any("osv-scanner" in x for x in sr.refused_tools({}, {**pins, "osv-scanner-enabled": True}))  # on, it is held to the same rule


def test_thresholds_red_what_they_say_and_every_waiver_carries_a_reason_an_issue_and_a_held_count():
    med = {**B602, "test_id": "B101", "issue_severity": "MEDIUM"}
    rows = sr.read_bandit({"results": [med]})
    assert not rows[0]["red"] and "B101" in sr.table(rows)  # a MEDIUM is in the table and the rung is green
    assert not sr.read_bandit({"results": [{**B602, "issue_confidence": "LOW"}]})[0]["red"]  # HIGH at LOW confidence is reported, not red
    assert not sr.read_semgrep({"results": [{"check_id": "r", "path": "a", "start": {"line": 1}, "extra": {"severity": "WARNING"}}]})[0]["red"]
    low = {"results": [{"packages": [{"package": {"name": "x"}, "groups": [{"ids": ["A"], "max_severity": "5.0"}], "vulnerabilities": [{"id": "A"}]}]}]}
    assert not sr.read_osv(low)[0]["red"]
    assert sr.read_osv(low, known_exploited=frozenset({"A"}))[0]["red"] and sr.read_osv(low, direct_fixable=frozenset({"x"}))[0]["red"]
    # a bare # nosec is refused naming the line; a reason and an issue pass
    assert "a.py:7" in sr.waiver_lint([("a.py", 7, "x()  # nosec")])[0]
    assert sr.waiver_lint([("a.py", 7, "x()  # nosec B602 -- argv list built from constants (#1234)")]) == []
    assert sr.waiver_lint([("a.swift", 2, "p() // nosemgrep: swift.process-shell")])
    assert sr.waiver_lint([("a.swift", 2, "p() // nosemgrep: swift.process-shell -- fixed argv (#55)")]) == []
    # a third nosemgrep with two on base and no approved issue is red; an approved one is not
    base, head = {"nosec": 1, "nosemgrep": 2}, {"nosec": 1, "nosemgrep": 3}
    assert "nosemgrep" in sr.waiver_ratchet(base, head, [9], lambda n: False)[0]
    assert sr.waiver_ratchet(base, head, [9], lambda n: True) == []
    assert sr.waiver_ratchet(base, head, [], lambda n: True)  # a raise naming no issue at all is not approved
    assert sr.waiver_counts({"a": "x  # nosec B1 -- r (#1)\ny // nosemgrep: r -- r (#2)\n"}) == {"nosec": 1, "nosemgrep": 1}
    # the baselines are held: more entries than on base is refused
    assert sr.baseline_raised("scripts/bandit_baseline.json", 10, 11) and not sr.baseline_raised("b", 10, 9)
    # an ignoreUntil too far out is refused; one inside 90 days with a reason passes
    today = dt.date(2026, 11, 14)
    far = '[[IgnoredVulns]]\nid = "GHSA-1"\nignoreUntil = 2027-06-02\nreason = "no fix yet"\n'
    near = '[[IgnoredVulns]]\nid = "GHSA-1"\nignoreUntil = 2027-01-01\nreason = "no fix yet"\n'
    assert "200 days" in sr.osv_config_problems(far, today)[0] or "days out" in sr.osv_config_problems(far, today)[0]
    assert sr.osv_config_problems(near, today) == []
    assert sr.osv_config_problems('[[IgnoredVulns]]\nid = "X"\nignoreUntil = 2027-01-01\n', today)  # no reason
    assert sr.gitleaks_config_problems('[allowlist]\nregexes = ["abc"]\n')  # no description
    assert sr.gitleaks_config_problems('[allowlist]\ndescription = "test fixture key (#9)"\nregexes = ["abc"]\n') == []


# ---- check_tool.security_lints against a real git repo, and the rung's skip rows and report-only behaviour

_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def _g(repo, *a):
    import os
    return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True, text=True, env={**os.environ, **_ENV}).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/a.py").write_text("x = 1\n")
    (tmp_path / "scripts/bandit_baseline.json").write_text(json.dumps({"results": [{"a": 1}, {"a": 2}]}))
    _g(tmp_path, "init", "-q", "-b", "main")
    _g(tmp_path, "add", "-A")
    _g(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _commit(repo, rel, text):
    (repo / rel).write_text(text)
    _g(repo, "add", "-A")
    _g(repo, "commit", "-qm", "c")
    return _g(repo, "rev-parse", "HEAD")


def _lints(repo, base, head, approved=lambda n: False):
    return check_tool.security_lints(repo, base, head, approved, dirs=("scripts",))


def test_the_waiver_lints_judge_a_real_diff(repo):
    base = _g(repo, "rev-parse", "HEAD")
    bare = _commit(repo, "scripts/a.py", "import os\nos.system(x)  # nosec\n")
    assert any("a.py:2" in p and "reason" in p for p in _lints(repo, base, bare))
    good = _commit(repo, "scripts/a.py", "import os\nos.system(x)  # nosec B605 -- fixed argv, no user text (#6601)\n")
    out = _lints(repo, base, good)
    assert not [p for p in out if "needs a rule" in p]
    assert any("raises the nosec waivers from 0 to 1" in p for p in out)  # a raised count needs an approved issue
    assert not _lints(repo, base, good, approved=lambda n: n == 6601)


def test_a_third_nosemgrep_is_red_unless_its_issue_is_approved(repo):
    lines = "".join(f"a{i} = 1  # nosemgrep: rule.x -- reason {i} (#7{i})\n" for i in range(3))
    base = _g(repo, "rev-parse", "HEAD")
    head = _commit(repo, "scripts/a.py", lines)
    assert any("nosemgrep waivers from 0 to 3" in p for p in _lints(repo, base, head))
    assert not _lints(repo, base, head, approved=lambda n: True)


def test_a_raised_baseline_is_red_and_a_shrunk_one_is_not(repo):
    base = _g(repo, "rev-parse", "HEAD")
    up = _commit(repo, "scripts/bandit_baseline.json", json.dumps({"results": [{}, {}, {}]}))
    assert any("may only shrink" in p for p in _lints(repo, base, up))
    down = _commit(repo, "scripts/bandit_baseline.json", json.dumps({"results": [{}]}))
    assert not _lints(repo, base, down)


def test_the_rung_skips_unconfigured_and_unrequired_batches_and_stays_green_while_report_only(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    assert check_tool.security(repo, "a", "b", ["scripts/x.py"], check_tool.Config())["skipped"]  # no [check.security]
    cfg = check_tool.Config(security={"enforce": False, "dirs": ["scripts"]})
    assert "not required" in check_tool.security(repo, "a", "b", ["docs/a.md"], cfg)["stdout_tail"]
    assert check_tool._report_only("security", {"enforce": False}, False, ["bandit B602 a.py:3"])["ok"]  # would-be red stays green
    assert [r for r in journal.read() if r["event"] == "alert" and r.get("rung") == "security"]
    assert not check_tool._report_only("security", {"enforce": True}, False, ["x"])["ok"]
    assert check_tool._timed_out_row("security", {"timed_out": True, "seconds": 9})["ok"]


def test_a_rung_that_did_not_measure_is_not_run_never_green_and_names_why(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    cfg = check_tool.Config(security={"enforce": False, "dirs": ["scripts"], "pins": {}}, build_remote="m4:/gate")
    refused = ["REFUSED: bandit has no pinned version in harness.toml [check.security]"]
    out = "SECURITY-RESULT " + json.dumps({"rows": [], "refused": refused, "table": "none"})
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": False, "skipped": False, "remote_env_red": True, "remote": "m4", "results": [{"ok": False, "exit_code": 1, "timed_out": False, "stdout_tail": out, "stderr_tail": "x"}]})
    r = check_tool.security(repo, "a", "b", ["scripts/x.py"], cfg)
    assert r["ok"] and r["not_run"] and "not-run: bandit refused" in r["stdout_tail"]
    rows = [x for x in journal.read() if x.get("state") == "not-run" and x.get("rung") == "security"]
    assert rows and rows[0].get("id") and "bandit" in rows[0]["reason"]
    # no SECURITY-RESULT line at all: the scan did not run, with the scanner's stderr kept
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": False, "skipped": False, "remote_env_red": True, "remote": "m4", "results": [{"ok": False, "exit_code": 1, "timed_out": False, "stdout_tail": "", "stderr_tail": "no module named x"}]})
    r = check_tool.security(repo, "a", "b", ["scripts/x.py"], cfg)
    assert r["not_run"] and "no module named x" in r["stdout_tail"]


def test_a_refused_scanner_does_not_hide_the_reds_of_the_scanners_that_ran(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    cfg = check_tool.Config(security={"enforce": False, "dirs": ["scripts"], "pins": {}}, build_remote="m4:/gate")
    red = {"scanner": "gitleaks", "rule": "generic-api-key", "where": "a.py:4", "red": True}
    out = "SECURITY-RESULT " + json.dumps({"rows": [red], "refused": ["REFUSED: bandit is not installed on the runner", "REFUSED: semgrep is not installed on the runner"], "table": "t"})
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": False, "skipped": False, "remote_env_red": True, "remote": "m4", "results": [{"ok": False, "exit_code": 1, "timed_out": False, "stdout_tail": out, "stderr_tail": ""}]})
    r = check_tool.security(repo, "a", "b", ["scripts/x.py"], cfg)
    assert r["not_run"] and "bandit, semgrep refused" in r["stdout_tail"] and "gitleaks generic-api-key a.py:4" in r["stdout_tail"]


# ---- #6589 item 10: the security rung runs on the build runner (`_remote_build`), never on this Mac

def _sec_cfg(**kw):
    sec = {"enforce": False, "dirs": ["scripts"], "pins": {}, "path": ["/opt/homebrew/bin", "/opt/tools/bin"], **kw}
    return check_tool.Config(security=sec, build_remote="m4:/gate")


def test_the_security_scan_goes_over_ssh_with_the_scanner_path_and_the_pin_check_first(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setattr(check_tool, "security_lints", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "_run", lambda *a, **k: pytest.fail("the security scan ran on this Mac"))
    out = "SECURITY-RESULT " + json.dumps({"rows": [], "refused": [], "table": "none"})
    monkeypatch.setattr(check_tool, "_remote_build", lambda root, cfg, cmd=(), name="build", reuse=True:
                        (seen.append((cmd, name, reuse)), {"ok": True, "skipped": False, "results": [{"ok": True, "exit_code": 0, "stdout_tail": out, "stderr_tail": ""}]})[1])
    r = check_tool.security(tmp_path, "a", "b", ["scripts/x.py"], _sec_cfg())
    assert r["ok"] and not r.get("not_run")
    (cmd, name, reuse), = seen
    assert name == "security" and reuse is False
    text = " ".join(cmd)
    assert "/opt/homebrew/bin:/opt/tools/bin" in text and "PATH=" in text
    assert text.index("install_security_tools.sh --check") < text.index("security_scan_run.py")  # the pin check, then the scan
    assert "--since a" in text and "--head b" in text


def test_an_unreachable_runner_is_a_not_run_row_with_the_reason_and_nothing_runs_here(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setattr(check_tool, "security_lints", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "_run", lambda *a, **k: pytest.fail("the security scan ran on this Mac"))
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: None)
    r = check_tool.security(tmp_path, "a", "b", ["scripts/x.py"], _sec_cfg())
    assert r["ok"] and r["not_run"] and "runner down" in r["stdout_tail"]
    assert [x for x in journal.read() if x.get("state") == "not-run" and x.get("rung") == "security"]
    # no runner configured at all: not-run too, never a run here
    r = check_tool.security(tmp_path, "a", "b", ["scripts/x.py"], check_tool.Config(security=_sec_cfg().security))
    assert r["not_run"] and "build_remote" in r["stdout_tail"]


def test_a_scan_that_exits_nonzero_on_the_runner_still_has_its_result_line_read(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    monkeypatch.setattr(check_tool, "security_lints", lambda *a, **k: [])
    red = {"scanner": "gitleaks", "rule": "k", "where": "a.py:4", "red": True}
    out = "SECURITY-RESULT " + json.dumps({"rows": [red], "refused": [], "table": "t"})
    row = {"ok": False, "exit_code": 1, "timed_out": False, "stdout_tail": out, "stderr_tail": ""}
    monkeypatch.setattr(check_tool, "_remote_build", lambda *a, **k: {"ok": False, "skipped": False, "remote_env_red": True, "remote": "m4", "results": [row]})
    r = check_tool.security(tmp_path, "a", "b", ["scripts/x.py"], _sec_cfg())
    assert "gitleaks k a.py:4" in r["stdout_tail"]
