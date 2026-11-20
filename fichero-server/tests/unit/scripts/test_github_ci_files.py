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
        assert (ROOT / u["directory"].lstrip("/")).is_dir(), u["directory"]
