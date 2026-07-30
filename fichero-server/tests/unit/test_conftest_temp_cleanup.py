"""The test suite must not leak its own storage (#4228).

`conftest.py` creates `fichero-tests-<pid>-*` per process for `FICHERO_BASE_PATH`
and, until this, never removed it. Four days of runs left **705 directories and
3.5 GB**, which exhausted the disk and produced ~45 SETUP errors in a full
suite — fixtures failing before any test body ran. Re-running to diagnose the
instability consumed more disk and made the next run likelier to die.

Two mechanisms, and the split is the point:

* an `atexit` finalizer removes this run's directory on a normal exit
* a startup sweep removes directories whose owning pid is GONE

The sweep is the durable half. **Every failed run that day ended in a kill**,
where no finalizer fires, so normal-exit cleanup alone would have prevented
none of the accumulation.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.gettempdir())
PREFIX = "fichero-tests-"


def _conftest_module():
    """Load the sweep helpers without re-importing the whole conftest."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location("_conftest_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheSweepIsSelective:
    """It must remove abandoned dirs and NEVER a running suite's."""

    def test_a_dead_pids_directory_is_removed(self, monkeypatch):
        conftest = _conftest_module()
        # pid 0 is never a real user process; _pid_is_alive reports it dead.
        abandoned = Path(tempfile.mkdtemp(prefix=f"{PREFIX}999999999-"))
        (abandoned / "app.duckdb").write_bytes(b"x")
        monkeypatch.setattr(conftest, "_pid_is_alive", lambda pid: False)

        conftest._sweep_abandoned_test_base_paths()

        assert not abandoned.exists(), "an abandoned directory survived the sweep"

    def test_a_live_pids_directory_is_NEVER_removed(self):
        """The safety property. Deleting a running suite's DuckDB is the one
        outcome worse than leaking."""
        conftest = _conftest_module()
        live = Path(tempfile.mkdtemp(prefix=f"{PREFIX}{os.getpid()}-"))
        try:
            conftest._sweep_abandoned_test_base_paths()

            assert live.exists(), "the sweep deleted a LIVE process's directory"
        finally:
            live.rmdir()

    def test_unrelated_directories_are_untouched(self):
        conftest = _conftest_module()
        stranger = Path(tempfile.mkdtemp(prefix="something-else-"))
        try:
            conftest._sweep_abandoned_test_base_paths()

            assert stranger.exists()
        finally:
            stranger.rmdir()

    def test_a_nonnumeric_pid_is_skipped_not_crashed(self):
        """A hand-made directory must not take the whole sweep down."""
        conftest = _conftest_module()
        odd = Path(tempfile.mkdtemp(prefix=f"{PREFIX}notapid-"))
        try:
            conftest._sweep_abandoned_test_base_paths()  # must not raise

            assert odd.exists()
        finally:
            odd.rmdir()


class TestPidLivenessErrsTowardAlive:
    """Under-cleaning is safe; deleting a live run's database is not."""

    def test_our_own_pid_is_alive(self):
        assert _conftest_module()._pid_is_alive(os.getpid())

    def test_an_impossible_pid_is_dead(self):
        assert not _conftest_module()._pid_is_alive(999_999_999)

    def test_a_permission_error_counts_as_alive(self, monkeypatch):
        """A dir owned by another user must never be swept."""
        conftest = _conftest_module()
        monkeypatch.setattr(
            conftest.os, "kill", lambda pid, sig: (_ for _ in ()).throw(PermissionError())
        )

        assert conftest._pid_is_alive(4242)


class TestCleanupActuallyFiresEndToEnd:
    """The requirement: prove it, don't assert the mechanism exists.

    Runs a real pytest session in a subprocess and checks it left nothing
    behind. Mutating the finalizer out of `conftest.py` makes this fail.
    """

    @pytest.mark.slow
    def test_a_completed_session_leaves_no_directory(self):
        """Runs a real test FROM THIS TREE, so `conftest.py` actually loads.

        A probe written into `tmp_path` would sit outside the rootdir, the
        conftest would never load, no directory would be created, and the
        assertion would pass while proving nothing. Found by mutation: with the
        finalizer deleted, that version stayed green.
        """
        root = Path(__file__).resolve().parents[3]
        target = root / "fichero-server" / "tests" / "unit" / "llm" / "test_lang_detect.py"
        assert target.is_file(), "the probe target moved; this test is now vacuous"

        # The child must mint its OWN base path. Inheriting ours points it at
        # this process's app.duckdb, which is held under an exclusive lock —
        # the child then dies on a concurrency error and never reaches cleanup.
        child_env = {k: v for k, v in os.environ.items() if k != "FICHERO_BASE_PATH"}
        child_env["PYTHONPATH"] = str(root / "fichero-server" / "src")

        # Judge the CHILD's directories, not the whole temp dir. A plain
        # before/after set diff calls any directory a concurrent pytest session
        # happens to create in the window a leak by THIS child — which is a
        # false failure whenever worker lanes run tests at the same time, and it
        # is the shape that made this test fail during a parallel run. The
        # conftest names each directory `fichero-tests-<pid>-*`, so the child's
        # own pid is the precise filter.
        child = subprocess.Popen(
            [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"],
            cwd=root,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, _ = child.communicate(timeout=300)
        assert child.returncode == 0, stdout.decode()[-500:]

        leaked = sorted(p.name for p in TMP.glob(f"{PREFIX}{child.pid}-*"))

        assert not leaked, f"session leaked: {leaked}"
