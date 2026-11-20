"""Spec: docs/contributor_manual/specs/harness/github-ci.md (ci.dependabot, ci.security-workflow, ci.test-workflow)."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]


def test_dependabot_yml_targets_integration_weekly_over_directories_that_exist():
    doc = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    assert doc["version"] == 2
    assert {u["package-ecosystem"] for u in doc["updates"]} == {"uv", "swift", "github-actions"}
    for u in doc["updates"]:
        assert u["target-branch"] == "integration"
        assert u["schedule"]["interval"] == "weekly"
        d = ROOT / u["directory"].lstrip("/")
        assert d.is_dir(), u["directory"]
        if u["package-ecosystem"] == "swift":
            assert (d / "Package.swift").is_file(), u["directory"]


def _workflow(name):
    doc = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    doc["on"] = doc.pop(True, doc.get("on"))  # YAML reads a bare `on` as True
    return doc


def test_security_workflow_runs_on_prs_and_nightly_reuses_the_rungs_scanner_and_adds_codeql():
    doc = _workflow("security.yml")
    assert set(doc["on"]) >= {"pull_request", "schedule"}
    assert doc["on"]["pull_request"]["branches"] == ["integration"]
    text = (ROOT / ".github/workflows/security.yml").read_text()
    assert "scripts/security_scan_run.py" in text
    assert 'sec["pins"]' in text and 'sec.get("osv"' in text and "uv tool install" in text and "install_security_tools" not in text
    assert 'if result["refused"]' in text
    assert {m["language"] for m in doc["jobs"]["codeql"]["strategy"]["matrix"]["include"]} == {"python", "swift"}


def test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job():
    doc = _workflow("tests.yml")
    assert doc["on"]["pull_request"]["branches"] == ["integration"]
    jobs = doc["jobs"]
    assert set(jobs) == {"engine", "swift"}
    assert all(j["continue-on-error"] is True and j["runs-on"] == "macos-15" for j in jobs.values())
    assert "enable-cache: true" in (ROOT / ".github/workflows/tests.yml").read_text()
