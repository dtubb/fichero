"""2026-11-27 11:16 (train-20261127-111606): green on every rung but security, where the iMac said "bandit/semgrep/gitleaks is not
installed on the runner", and the train went back red. A runner's missing tool is the runner's fault, never a step's red."""
from __future__ import annotations

import pytest

from fichero_builder import check_tool, journal, measure


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "harness.toml").write_text(
        '[check]\nbuild_remote = "imac:~/g"\nremote = ["imac:~/g", "imac:~/g2", "air:~/g", "m4:~/g"]\n'
        '[check.security]\nenforce = true\ndirs = ["src"]\npins = { bandit = "1.9.4", semgrep = "1.185.0", gitleaks = "8.30.1" }\n')
    monkeypatch.setattr(check_tool, "security_lints", lambda *a, **k: [])
    monkeypatch.setattr(check_tool, "RUNNER_ALERTED", set())
    alerts = []
    from fichero_builder import queue
    monkeypatch.setattr(queue, "alert", lambda *a, **k: alerts.append(a))
    return check_tool.load(tmp_path), alerts


def test_a_runner_without_the_pinned_scanners_hands_the_scan_to_the_next_runner_that_has_them(cfg, monkeypatch):
    c, alerts = cfg
    tried = []

    def on(root, since, head, cc, problems, pins, osv_on):
        tried.append(cc.build_remote)
        if cc.build_remote.startswith("imac"):
            return {"_runner_refused": ["bandit", "semgrep", "gitleaks"]}
        return {"name": "security", "ok": True, "stdout_tail": "no new finding", "results": []}
    monkeypatch.setattr(check_tool, "_security_on", on)
    r = check_tool.security("/r", "a", "b", ["src/x.py"], c)
    assert r["ok"] and not r.get("not_run") and tried == ["imac:~/g", "air:~/g"], "the iMac once (its second folder is the same Mac), then the Air"
    assert not alerts


def test_with_no_runner_holding_the_scanners_the_rung_is_not_run_never_red_and_one_alert_names_the_runners(cfg, monkeypatch):
    c, alerts = cfg
    monkeypatch.setattr(check_tool, "_security_on", lambda *a: {"_runner_refused": ["bandit"]})
    for _ in range(2):
        r = check_tool.security("/r", "a", "b", ["src/x.py"], c)
        assert r["ok"] and r["not_run"] and r["infra"], "an infra fault: never a step's red, enforce or not"
    assert len(alerts) == 1 and "imac:~/g: bandit" in alerts[0][2] and "air:~/g: bandit" in alerts[0][2] and "machines scanners --install" in alerts[0][2]
    assert [x["state"] for x in journal.read() if x.get("state") == "runner-tools-missing"] == ["runner-tools-missing"] * 2


def test_only_a_runner_fault_moves_the_scan_on_and_the_preflight_holds_each_tool_to_its_pin():
    assert check_tool.RUNNER_FAULT.match("REFUSED: bandit is not installed on the runner")[1] == "bandit"
    assert check_tool.RUNNER_FAULT.match("REFUSED: semgrep is 1.187.0 on the runner, the pin is 1.185.0")[1] == "semgrep"
    assert not check_tool.RUNNER_FAULT.match("REFUSED: gitleaks has no pinned version in harness.toml [check.security]"), "a config gap stays a refusal"
    pins = {"bandit": "1.9.4", "semgrep": "1.185.0", "gitleaks": "8.30.1"}
    tools = list(pins)
    assert measure.scanner_problems({"bandit": "1.9.4", "semgrep": "1.187.0"}, pins, tools) == [
        "semgrep is 1.187.0, the pin is 1.185.0", "gitleaks is not installed, the pin is 8.30.1"]
    script = measure._scanner_install(pins, tools)
    assert "uv tool install --force bandit==1.9.4" in script and "uv tool install --force semgrep==1.185.0" in script
    assert "gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_darwin_" in script and '-C "$HOME/.local/bin" gitleaks' in script
    assert measure.SCANNER_PATH.startswith('"$HOME/.local/bin":/opt/homebrew/bin'), "the rung's own PATH (check_tool.SECURITY_PATH)"
