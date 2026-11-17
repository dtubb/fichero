"""#6663: a committed .xcscheme/.xcconfig/.plist under fichero/ must not carry a home-folder path."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "scripts" / "check_no_home_paths_in_project.py"


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, timeout=60)


def _repo(tmp_path: Path, body: str) -> Path:
    (tmp_path / "fichero").mkdir()
    (tmp_path / "fichero" / "a.xcscheme").write_text(body)
    return tmp_path


def test_a_home_path_in_a_tracked_scheme_fails(tmp_path):
    home = "/" + "Users" + "/someone"  # assembled, so the test file itself holds no home path
    done = _run(_repo(tmp_path, f'value = "{home}/Library/x.sock"\n'))
    assert done.returncode == 1 and "a.xcscheme:1" in done.stdout


def test_a_clean_scheme_passes(tmp_path):
    assert _run(_repo(tmp_path, 'value = "1"\n')).returncode == 0


def test_a_tree_with_nothing_to_scan_fails(tmp_path):
    assert _run(tmp_path).returncode == 2


def test_the_real_tree_is_clean():
    done = _run(REPO)
    assert done.returncode == 0, done.stdout
