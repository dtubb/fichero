"""`fichero_server.core.fast_exit.leave` (#5929, `runtime.torch.exits-cleanly`): with torch loaded the engine leaves by `os._exit`
with its own status after every database is closed; without torch, or with a database that will not close, it returns and the
ordinary exit follows. A stand-in `torch` module stands for the real one, so the cases run anywhere with DuckDB."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import duckdb

SRC = Path(__file__).resolve().parents[3] / "src"
TORCH = "import types; sys.modules['torch'] = types.ModuleType('torch')\n"


def _run(tmp_path: Path, body: str, *, torch: bool = False) -> subprocess.CompletedProcess:
    # The body is dedented BEFORE the stand-in torch line is put in front of it (dedenting both left the indented body
    # an IndentationError), and this tree's src is on the path twice, absolute: a relative one, or the venv's installed
    # (older) copy, is what the gate's inner runs fell over (cd4334778).
    code = f"import sys; sys.path.insert(0, {str(SRC)!r})\n" + (TORCH if torch else "") + textwrap.dedent(body)
    env = {**os.environ, "FICHERO_BASE_PATH": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": str(SRC)}
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=300)


def test_without_torch_leave_returns(tmp_path):
    done = _run(tmp_path, "from fichero_server.core.fast_exit import leave\nleave(7)\nprint('returned')\n")
    assert done.returncode == 0 and "returned" in done.stdout, done.stderr


def test_with_torch_leave_exits_with_the_status_and_returns_never(tmp_path):
    done = _run(tmp_path, "from fichero_server.core.fast_exit import leave\nleave(7)\nprint('returned')\n", torch=True)
    assert done.returncode == 7 and "returned" not in done.stdout, done.stderr


def test_a_library_written_before_leave_reopens_with_no_wal_to_replay(tmp_path):
    package = tmp_path / "lib.fichero"
    done = _run(tmp_path, f'''
        from pathlib import Path
        from fichero_server.db.manager import db_manager
        from fichero_server.core.fast_exit import leave
        package = Path({str(package)!r})
        for sub in ("lance", "storage", "files"):
            (package / sub).mkdir(parents=True, exist_ok=True)
        db = db_manager.get_database(package)
        db.execute("CREATE TABLE IF NOT EXISTS t5929 (x INTEGER)")
        db.execute("INSERT INTO t5929 VALUES (1), (2), (3)")
        leave(0)
        print("returned")
    ''', torch=True)
    assert done.returncode == 0 and "returned" not in done.stdout, done.stderr
    db_file = next(package.glob("*.duckdb"))
    assert not Path(str(db_file) + ".wal").exists(), "a WAL left behind would replay at the next open (the index hazard)"
    con = duckdb.connect(str(db_file), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM t5929").fetchone()[0] == 3
    finally:
        con.close()


def test_a_database_that_will_not_close_takes_the_ordinary_exit(tmp_path):
    done = _run(tmp_path, '''
        from fichero_server.core import fast_exit
        fast_exit.close_everything = lambda: (_ for _ in ()).throw(RuntimeError("still open: ['x']"))
        fast_exit.leave(0)
        print("returned")
    ''', torch=True)
    assert done.returncode == 0 and "returned" in done.stdout and "fast exit skipped" in done.stderr, done.stderr


def test_a_systemexit_message_is_printed_and_the_status_is_one(tmp_path):
    done = _run(tmp_path, "from fichero_server.core.fast_exit import leave\nleave(1, 'refusing a plaintext listener')\nprint('returned')\n",
                torch=True)
    assert done.returncode == 1 and "refusing a plaintext listener" in done.stderr and "returned" not in done.stdout


def test_a_thumbnail_being_written_finishes_before_the_process_leaves(tmp_path):
    marker = tmp_path / "thumb.done"
    done = _run(tmp_path, f'''
        import time
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        from fichero_server.db import storage
        from fichero_server.core.fast_exit import leave
        storage._executor = ThreadPoolExecutor(1)
        storage._executor.submit(lambda: (time.sleep(0.5), Path({str(marker)!r}).write_text("x")))
        time.sleep(0.1)
        leave(0)
    ''', torch=True)
    assert done.returncode == 0 and marker.exists(), done.stderr
