"""dev-workflows run.slice-zero item 3: the handoff hook starts successors only through harness_start.py."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_the_hook_self_check_passes():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "harness_handoff_hook.py"), "--test"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
