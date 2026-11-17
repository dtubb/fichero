"""The Performance and Security lenses in every review prompt, and the security surface at its top (#6600, Step 2.29).

The reviewer is a model, so what is tested is what it is GIVEN: the rendered prompt carries the named checks, the
fixture diff the check must catch, the surface list at the top, and still ends by asking for the one verdict line."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "harness_review.py"
MODELS = '[models]\nproviders = ["claude-code"]\nreviewer = { provider = "claude-code", model = "opus", context = 200000 }\n'


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_BUILDER_STATE", str(tmp_path / "state"))


def _prompt(tmp_path, files: dict[str, str], ladder: Path | None = None) -> str:
    repo = tmp_path / "r"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    (repo / "base.txt").write_text("x\n")
    g("add", "."), g("commit", "-q", "-m", "base"), g("branch", "landbr")
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    g("add", "."), g("commit", "-q", "-m", "change")
    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / "harness.toml").write_text('[land]\nbranch = "landbr"\n' + MODELS)
    r = subprocess.run([sys.executable, str(SCRIPT), str(repo), "HEAD", "--pinned", str(pinned), "--verdicts", str(tmp_path / "v.json"), "--print",
                        *(["--ladder", str(ladder)] if ladder else [])],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_the_performance_lens_is_in_the_prompt_and_a_store_wide_observation_and_an_n_plus_one_each_draw_a_finding(tmp_path):
    swift = "struct Row: View {\n    @Environment(Store.self) var store\n    var body: some View { Text(store.items[0].name) }\n}\n"
    engine = 'def names(conn, ids):\n    for id in ids:\n        conn.execute("SELECT name FROM t WHERE id = ?", [id])\n'
    p = _prompt(tmp_path, {"fichero/Row.swift": swift, "fichero-server/src/q.py": engine})
    assert "LENS: Performance (speed, memory, disk)" in p
    for named in ("App (Swift, macOS and iOS)", "Engine (Python, fichero-server)", "a `body` that observes a whole store",
                  "a query inside a loop where one IN or a join does", "#6547", "countLimit"):
        assert named in p
    assert "store.items[0].name" in p and "WHERE id = ?" in p  # the fixture diffs are what the check is read against
    assert "the cheaper way named" in p  # a finding names the cheaper way
    assert p.rstrip().endswith("READY: allow-shadow <path>, <path>.")  # the one verdict line is still the last ask


def test_the_security_lens_is_in_the_prompt_a_shell_call_draws_a_finding_and_an_entitlement_change_is_listed_at_the_top(tmp_path):
    shell = 'import subprocess\ndef conv(name):\n    subprocess.run(f"convert {name}", shell=True)\n'
    p = _prompt(tmp_path, {"scripts/conv.py": shell, "fichero/fichero/Fichero.entitlements": "<plist/>\n"})
    assert "LENS: Security." in p and "a subprocess with shell=True" in p and "the safe form named (for a shell call, the argument list)" in p
    assert 'subprocess.run(f"convert {name}", shell=True)' in p
    top = p.split("CHECKLIST:")[0]
    assert "SECURITY SURFACE CHANGED: fichero/fichero/Fichero.entitlements" in top
    assert p.rstrip().endswith("READY: allow-shadow <path>, <path>.")


def test_a_diff_with_no_surface_lists_none_at_the_top(tmp_path):
    p = _prompt(tmp_path, {"docs/a.md": "hello\n"})
    assert "SECURITY SURFACE CHANGED: none" in p.split("CHECKLIST:")[0]
    assert "LENS: Security." in p and "LENS: Performance" in p


def test_the_security_rung_s_table_is_in_the_prompt_under_security_scan_exactly_as_the_rung_made_it(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "fichero-builder"))
    from fichero_builder import security_rung as sr
    rows = sr.read_bandit({"results": [{"filename": "scripts/conv.py", "line_number": 3, "test_id": "B602", "issue_severity": "HIGH",
                                        "issue_confidence": "HIGH", "issue_text": "shell=True", "code": "x"}]})
    table = sr.table(rows)
    ladder = tmp_path / "ladder.json"
    ladder.write_text(json.dumps({"ok": True, "rungs": [{"name": "guards", "ok": True}, {"name": "security", "ok": True, "table": table}]}))
    p = _prompt(tmp_path, {"scripts/conv.py": "x = 1\n"}, ladder)
    assert f"SECURITY SCAN (new findings only):\n{table}\n" in p and "bandit | B602" in p
    ladder.write_text(json.dumps({"ok": True, "rungs": [{"name": "security", "ok": True, "skipped": True, "stdout_tail": "not required: x"}]}))
    (tmp_path / "b").mkdir()
    assert "(skipped: not required: x)" in _prompt(tmp_path / "b", {"scripts/conv.py": "x = 1\n"}, ladder)


def test_a_nested_route_module_is_on_the_security_surface_at_the_top(tmp_path):
    nested = "fichero-server/src/fichero_server/api/routes/auth/authz.py"
    p = _prompt(tmp_path, {nested: "def check(user):\n    return True\n", "fichero-server/src/fichero_server/api/routes/ai/provider_keys.py": "x = 1\n"})
    top = p.split("CHECKLIST:")[0]
    assert top.count("SECURITY SURFACE CHANGED:") == 1 and nested in top and "ai/provider_keys.py" in top and "none" not in top.split("SECURITY SURFACE CHANGED:")[1]
