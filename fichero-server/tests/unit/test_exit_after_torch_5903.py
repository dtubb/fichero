"""`tests/_exit_after_torch.py` (#5903): the suite's process leaves with `os._exit` once torch is loaded, without losing the exit code
or a write. Real inner pytest runs in a subprocess, with a stand-in `torch` module so the hook fires without importing the real one."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import duckdb

ENGINE_ROOT = Path(__file__).resolve().parents[2]

CONFTEST = '''
import os, sys, types
sys.path.insert(0, {tests_parent!r})
sys.modules.setdefault("torch", types.ModuleType("torch"))   # the hook runs only with torch loaded
import pytest
from tests import _exit_after_torch

_real_exit = os._exit
def _marked_exit(code):
    open({marker!r}, "w").write(str(code))
    _real_exit(code)
_exit_after_torch.os._exit = _marked_exit

def pytest_configure(config):
    _exit_after_torch.register(config)
'''


def _say(proc) -> str:
    return f"\n--- inner pytest stdout ---\n{proc.stdout[-3000:]}\n--- stderr ---\n{proc.stderr[-3000:]}"


def _run(tmp_path: Path, test_source: str) -> tuple[int, Path, str]:
    marker = tmp_path / "fast-exit-marker"
    (tmp_path / "conftest.py").write_text(CONFTEST.format(tests_parent=str(ENGINE_ROOT), marker=str(marker)))
    (tmp_path / "test_inner.py").write_text(textwrap.dedent(test_source))
    env = {**os.environ, "FICHERO_BASE_PATH": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1",
           # the inner run starts in tmp_path, so a relative PYTHONPATH (the gate passes "src") would miss this tree
           # and import whatever fichero_server the venv has installed
           "PYTHONPATH": os.pathsep.join([str(ENGINE_ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
                           str(tmp_path / "test_inner.py")], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    return proc.returncode, marker, _say(proc)


def test_a_failing_inner_run_still_exits_non_zero(tmp_path):
    code, marker, said = _run(tmp_path, "def test_fails():\n    assert False\n")
    assert code == 1, "pytest's own status (1 = tests failed), never 0" + said
    assert marker.exists() and marker.read_text() == "1", "the fast exit was taken, with that status" + said


def test_a_passing_inner_run_exits_zero_by_the_fast_path(tmp_path):
    code, marker, said = _run(tmp_path, "def test_ok():\n    assert True\n")
    assert code == 0 and marker.exists() and marker.read_text() == "0", said


def test_a_library_written_in_the_run_reopens_with_no_wal_to_replay(tmp_path):
    package = tmp_path / "lib.fichero"
    code, marker, said = _run(tmp_path, f'''
        from pathlib import Path
        from fichero_server.db.manager import db_manager

        def test_writes():
            package = Path({str(package)!r})
            for sub in ("lance", "storage", "files"):
                (package / sub).mkdir(parents=True, exist_ok=True)
            db = db_manager.get_database(package)
            db.execute("CREATE TABLE IF NOT EXISTS t5903 (x INTEGER)")
            db.execute("INSERT INTO t5903 VALUES (1), (2), (3)")
    ''')
    assert code == 0 and marker.exists() and marker.read_text() == "0", "the fast exit was taken" + said
    db_file = next(package.glob("*.duckdb"))
    assert not Path(str(db_file) + ".wal").exists(), "a WAL left behind would replay at the next open (the index hazard)"
    con = duckdb.connect(str(db_file), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM t5903").fetchone()[0] == 3
    finally:
        con.close()


def test_without_torch_the_ordinary_exit_is_taken(tmp_path):
    (tmp_path / "conftest.py").write_text(CONFTEST.format(tests_parent=str(ENGINE_ROOT), marker=str(tmp_path / "m")).replace(
        'sys.modules.setdefault("torch", types.ModuleType("torch"))', "pass"))
    (tmp_path / "test_inner.py").write_text("def test_ok():\n    assert True\n")
    env = {**os.environ, "FICHERO_BASE_PATH": str(tmp_path / "state"),
           "PYTHONPATH": os.pathsep.join([str(ENGINE_ROOT / "src"), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
                           str(tmp_path / "test_inner.py")], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0 and not (tmp_path / "m").exists()
