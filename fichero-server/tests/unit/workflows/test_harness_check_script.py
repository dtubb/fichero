"""tool.check script: refuses to run the ladder as the owner when the rules file has no [jail] (#6116)."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "harness_check.py"


def test_check_script_refuses_without_jail(tmp_path):
    (tmp_path / "harness.toml").write_text("[check]\n")
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "HEAD", "HEAD", "--pinned", str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode != 0
    assert "jail" in (r.stderr + r.stdout).lower()
