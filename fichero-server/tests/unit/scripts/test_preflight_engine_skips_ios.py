"""The iOS build runs the embedded-engine build phase too; it must stage nothing and pass (2026-11-18 iOS TestFlight preflight)."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "preflight-embedded-engine.sh"


def test_an_ios_build_stages_no_engine_and_passes() -> None:
    env = {**os.environ, "PLATFORM_NAME": "iphoneos", "PATH": "/usr/bin:/bin"}  # Xcode's minimal PATH: no venv python
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "No embedded engine for iphoneos" in r.stdout
