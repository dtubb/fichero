"""The `security` rung: each scanner's new findings red it, a baselined one does not, a missing scanner refuses; the thresholds and
the waivers (#6600, Step 2.30). The scanners' JSON outputs are the fixtures: no scanner binary runs here."""
import datetime as dt

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
