"""The repo's `scripts/gitleaks.toml` passes the harness's own lint: every allowlist is by regexes or paths and says why
(`scan-thresholds-and-waivers`, 2026-11-27). The repo root takes no new file (`code-org.folders.root`), so gitleaks does not find
the file by itself: `scripts/security_scan_run.py` names it with `--config`."""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "fichero-builder"))


def test_every_allowlist_has_a_reason_and_a_narrow_match():
    from fichero_builder import security_rung

    text = (ROOT / "scripts" / "gitleaks.toml").read_text()
    assert security_rung.gitleaks_config_problems(text) == []
    doc = tomllib.loads(text)
    assert doc["extend"]["useDefault"] is True, "the default rules stay; the file only allowlists"
    assert len(doc["allowlists"]) >= 3


def test_the_scan_names_the_config_since_gitleaks_only_looks_for_it_at_the_root():
    assert not (ROOT / ".gitleaks.toml").exists(), "the root holds no scanner config (check_file_placement)"
    assert '"--config", "scripts/gitleaks.toml"' in (ROOT / "scripts" / "security_scan_run.py").read_text()
