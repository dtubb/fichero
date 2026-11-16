"""dev-workflows run.slice-zero item 3: the handoff hook starts successors only through harness_start.py."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_the_hook_self_check_passes():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "harness_handoff_hook.py"), "--test"], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


def test_a_successor_keeps_the_builder_name_so_its_hooks_find_the_registry(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("hh", ROOT / "scripts" / "harness_handoff_hook.py")
    hh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hh)
    seen = []
    hh.start_successor("b", {"worktree": "/w", "handoff": "H.md"}, 3, lambda c, **k: seen.append(c))
    assert seen[0][seen[0].index("--name") + 1] == "b"
