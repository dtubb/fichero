"""The repo's `.gitleaks.toml` passes the harness's own lint: every allowlist is by regexes or paths and says why
(`scan-thresholds-and-waivers`, 2026-11-27). gitleaks reads it from the repo root for the security rung's scan."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "fichero-builder"))


def test_every_allowlist_has_a_reason_and_a_narrow_match():
    from fichero_builder import security_rung

    text = (ROOT / ".gitleaks.toml").read_text()
    assert security_rung.gitleaks_config_problems(text) == []
    doc = tomllib.loads(text)
    assert doc["extend"]["useDefault"] is True, "the default rules stay; the file only allowlists"
    assert len(doc["allowlists"]) >= 3
