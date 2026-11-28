"""The repo's own semgrep rules exist and are well formed (`dev-workflows.quality.security-scan-rung`, 2026-11-27).

`scripts/security_scan_run.py` passes `--config .semgrep/` to every semgrep run; until this folder existed semgrep exited 7
(no such config) and wrote no JSON, so the rung said REFUSED on every batch and the semgrep half never scanned. Each rule
here is one the spec names as what `p/swift` lacks.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
RULES_DIR = ROOT / ".semgrep"
NAMED = {"fichero.swift-process-shell", "fichero.swift-keyed-unarchiver-without-secure-coding", "fichero.plist-allows-arbitrary-loads"}


def _rules() -> list[dict]:
    files = sorted(RULES_DIR.glob("*.yml"))
    assert files, f"{RULES_DIR} holds no rules: semgrep refuses the config and the rung never scans"
    return [rule for f in files for rule in yaml.safe_load(f.read_text())["rules"]]


def test_the_scan_driver_names_the_folder_and_it_exists():
    assert ".semgrep/" in (ROOT / "scripts" / "security_scan_run.py").read_text()
    assert RULES_DIR.is_dir()


def test_every_rule_is_well_formed_and_the_named_ones_are_there():
    rules = _rules()
    ids = {r["id"] for r in rules}
    assert NAMED <= ids, NAMED - ids
    for r in rules:
        assert r["id"].startswith("fichero."), r["id"]
        assert r["message"] and r["severity"] in {"ERROR", "WARNING", "INFO"} and r["languages"], r["id"]
        assert any(k in r for k in ("pattern", "pattern-either", "patterns", "pattern-regex")), r["id"]
