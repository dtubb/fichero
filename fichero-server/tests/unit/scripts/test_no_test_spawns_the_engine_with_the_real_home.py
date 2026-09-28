"""The guard that stops a test spawning the engine with the maintainer's real HOME (#5187).

WHY: see tests/_engine_home_guard.py -- two spawners did it, and a real-HOME engine walks his real
libraries at startup. The guard must refuse the old shape (the env test_transport_round_trips
built before the fix, reproduced below), pass the shape every fixed spawner uses, leave other
subprocesses alone, and be live on `subprocess.Popen` for the whole session.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests._engine_home_guard import REAL_HOME, GuardedPopen, engine_spawn_problem

ENGINE = ["/venv/bin/python", "-m", "uvicorn", "fichero_server.api.uds_transport:app", "--uds", "/tmp/e.sock"]


def _old_transport_env(base_path: Path, token: str) -> dict[str, str]:
    """test_transport_round_trips._child_env as it was before #5187: no HOME, so the real one."""
    env = dict(os.environ)
    env["HOME"] = REAL_HOME          # what dict(os.environ) carries in a normal session
    env.update(
        FICHERO_BASE_PATH=str(base_path),
        FICHERO_BOOTSTRAP_TOKEN=token,
        FICHERO_TOKEN_DIR=str(base_path / "token"),
        FICHERO_MULTIUSER="0",
        FICHERO_FEATURE_TIER="dev",
        FICHERO_SKIP_DEFAULT_WORKFLOWS="1",
    )
    env.pop("FICHERO_DISABLE_AUTH", None)
    return env


def test_the_old_transport_env_is_refused(tmp_path):
    problem = engine_spawn_problem(ENGINE, _old_transport_env(tmp_path, "t"))
    assert problem and "real libraries" in problem


def test_an_engine_with_its_own_temp_home_is_allowed(tmp_path):
    assert engine_spawn_problem(ENGINE, {**os.environ, "HOME": str(tmp_path / "home")}) is None
    assert engine_spawn_problem(ENGINE, {**os.environ, "HOME": tempfile.mkdtemp()}) is None


def test_a_home_outside_temp_or_missing_is_refused():
    assert engine_spawn_problem(ENGINE, {"HOME": "/Users/someone-else"})
    assert engine_spawn_problem(ENGINE, {"PATH": "/usr/bin"}) == "spawns the engine with no HOME"


def test_other_subprocesses_are_not_judged():
    assert engine_spawn_problem(["git", "status"], {"HOME": REAL_HOME}) is None
    # an import probe starts no engine (test_engine_starts_without_unbundled_packages)
    assert engine_spawn_problem(["python", "-c", "import fichero_server.api.uds_transport"], {"HOME": REAL_HOME}) is None
    assert engine_spawn_problem(["uvicorn", "--help"], {"HOME": REAL_HOME}) is None


def test_the_guard_is_live_and_refuses_before_anything_starts(tmp_path):
    """Installed by the root conftest for every session; it refuses BEFORE exec -- the path below
    does not exist, so reaching exec would raise FileNotFoundError instead."""
    assert subprocess.Popen is GuardedPopen
    with pytest.raises(AssertionError, match="real libraries"):
        subprocess.Popen([str(tmp_path / "no-such" / "uvicorn"), "fichero_server.api.tcp_transport:app"],
                         env=_old_transport_env(tmp_path, "t"))
