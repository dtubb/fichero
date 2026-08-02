"""The coverage ratchet guardrail FIRES (#4249).

Guardrails must match granularity: every rule ships with a fixture proving it
fires. These tests run scripts/check_coverage_ratchet.py against synthetic
coverage reports in test-fixtures/coverage-ratchet/ and assert both the
firing (exit 1) and passing (exit 0) directions, plus the deliberate
--update-baseline path.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check_coverage_ratchet.py"
FIXTURES = REPO_ROOT / "test-fixtures" / "coverage-ratchet"


def run_ratchet(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestRatchetFires:
    def test_engine_drop_fires(self):
        r = run_ratchet(
            "--engine-json", str(FIXTURES / "engine_low.json"),
            "--baseline", str(FIXTURES / "baseline_high.json"),
        )
        assert r.returncode == 1, r.stdout + r.stderr
        assert "coverage ratchet FAILED" in r.stdout

    def test_swift_drop_fires(self):
        r = run_ratchet(
            "--swift-json", str(FIXTURES / "swift_low.json"),
            "--baseline", str(FIXTURES / "baseline_high.json"),
        )
        assert r.returncode == 1, r.stdout + r.stderr
        assert "swift" in r.stdout

    def test_least_covered_report_lists_worst_production_file_first(self):
        r = run_ratchet(
            "--swift-json", str(FIXTURES / "swift_low.json"),
            "--baseline", str(FIXTURES / "baseline_low.json"),
        )
        body = r.stdout
        assert "DocumentStore.swift" in body
        # test bundles are excluded from the least-covered report
        assert "DocumentStoreTests.swift" not in body
        assert body.index("DocumentStore.swift") < body.index("APIClient.swift")


class TestRatchetPasses:
    def test_at_or_above_baseline_passes(self):
        r = run_ratchet(
            "--engine-json", str(FIXTURES / "engine_low.json"),
            "--swift-json", str(FIXTURES / "swift_low.json"),
            "--baseline", str(FIXTURES / "baseline_low.json"),
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "OK" in r.stdout

    def test_argless_without_artifacts_is_not_armed_but_green(self):
        r = run_ratchet()
        assert r.returncode == 0, r.stdout + r.stderr
        assert "NOT ARMED" in r.stdout


class TestUpdateBaseline:
    def test_update_baseline_records_measured_values(self, tmp_path):
        baseline = tmp_path / "baseline.json"
        shutil.copyfile(FIXTURES / "baseline_high.json", baseline)
        r = run_ratchet(
            "--engine-json", str(FIXTURES / "engine_low.json"),
            "--baseline", str(baseline),
            "--update-baseline",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        updated = json.loads(baseline.read_text())
        assert updated["engine"]["line_rate_pct"] == 41.5
        # untouched stacks keep their recorded value
        assert updated["swift"]["line_rate_pct"] == 60.0

    def test_missing_baseline_fails_loudly(self):
        r = run_ratchet(
            "--engine-json", str(FIXTURES / "engine_low.json"),
            "--baseline", str(FIXTURES / "does_not_exist.json"),
        )
        out = r.stdout + r.stderr
        # BLIND (exit 2), not a violation (exit 1): "I could not read the
        # baseline I compare against" is not "coverage regressed" (#4487).
        assert r.returncode == 2, f"expected BLIND, got {r.returncode}: {out}"
        # Assert the PROPERTY the message must carry — it names the path it
        # could not read — not the wording. This test previously pinned the
        # literal string "cannot read" and went red when #4487 improved the
        # message without changing the behaviour. A test that fails on better
        # prose is a test about prose.
        assert "does_not_exist.json" in out, out
