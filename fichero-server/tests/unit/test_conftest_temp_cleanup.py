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


# ---------------------------------------------------------------------------
# #4434 — the OTHER temp tree: pytest's own basetemps (pytest-of-<user>)
# ---------------------------------------------------------------------------
# 77 GB of `pytest-of-danieltubb/pytest-N` run dirs filled the disk on
# 2026-07-30. They are created by tmp_path/tmp_path_factory — outside the
# `fichero-tests-*` sweep above — and a SIGKILLed run (the gate watchdog)
# leaves its dir WITH its .lock, which pytest's own collector then ignores
# for an hour. `_sweep_abandoned_pytest_basetemps` is the counterpart sweep.

import time  # noqa: E402 — file keeps narrative order; matches conftest's own style


def _run_dir(base: Path, name: str, *, lock_pid=None, age_s: float = 3600) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "payload.duckdb").write_bytes(b"x")
    if lock_pid is not None:
        (d / ".lock").write_text(str(lock_pid))
    old = time.time() - age_s
    os.utime(d, (old, old))
    return d


class TestPytestBasetempSweep:
    def test_a_dead_pids_locked_dir_is_removed(self, tmp_path):
        """A killed run cannot leak — its lock names a pid that is gone."""
        conftest = _conftest_module()
        base = tmp_path / "pytest-of-user"
        dead = _run_dir(base, "pytest-3", lock_pid=999_999_999)

        removed = conftest._sweep_abandoned_pytest_basetemps(base)

        assert not dead.exists(), "a dead run's locked dir survived the sweep"
        assert removed == 1

    def test_a_live_pids_locked_dir_is_NEVER_removed(self, tmp_path):
        """The safety property: a concurrent lane's run must not be touched."""
        conftest = _conftest_module()
        base = tmp_path / "pytest-of-user"
        live = _run_dir(base, "pytest-4", lock_pid=os.getpid())

        conftest._sweep_abandoned_pytest_basetemps(base)

        assert live.exists(), "the sweep deleted a LIVE run's basetemp"

    def test_lockless_dirs_keep_only_the_newest(self, tmp_path):
        """Finished runs: ONE most-recent may stay (the retained run,
        tmp_path_retention_count=1); everything older goes."""
        conftest = _conftest_module()
        base = tmp_path / "pytest-of-user"
        oldest = _run_dir(base, "pytest-1", age_s=7200)
        newer = _run_dir(base, "pytest-2", age_s=3600)

        conftest._sweep_abandoned_pytest_basetemps(base)

        assert newer.exists(), "the single retained run was deleted"
        assert not oldest.exists(), "an older finished run survived"

    def test_a_young_lockless_dir_survives_the_race_guard(self, tmp_path):
        """pytest creates the dir a moment before writing its lock; a starting
        concurrent run must not lose that race."""
        conftest = _conftest_module()
        base = tmp_path / "pytest-of-user"
        _run_dir(base, "pytest-1", age_s=7200)  # the kept newest-lockless
        fresh = _run_dir(base, "pytest-9", age_s=0)

        conftest._sweep_abandoned_pytest_basetemps(base)

        assert fresh.exists(), "a just-created (pre-lock) run dir was deleted"

    def test_a_garbage_lock_counts_as_dead(self, tmp_path):
        """An unreadable lock is a corpse, not a claim."""
        conftest = _conftest_module()
        base = tmp_path / "pytest-of-user"
        corpse = _run_dir(base, "pytest-5")
        (corpse / ".lock").write_text("not-a-pid")

        conftest._sweep_abandoned_pytest_basetemps(base)

        assert not corpse.exists()

    def test_a_missing_root_is_a_noop(self, tmp_path):
        assert _conftest_module()._sweep_abandoned_pytest_basetemps(
            tmp_path / "does-not-exist"
        ) == 0


class TestBasetempSweepFiresOnAbnormalExit:
    """The requirement (#4434, and today's recurring lesson): prove the guard
    fires on the ABNORMAL path, not just the happy one. A real pytest child is
    SIGKILLed mid-test — the exact thing the gate watchdog does — and must
    leak its basetemp with a dead-pid lock; the sweep must then reclaim it."""

    @pytest.mark.slow
    def test_a_sigkilled_run_leaks_and_the_sweep_reclaims_it(self, tmp_path):
        import signal

        project = tmp_path / "proj"
        project.mkdir()
        (project / "test_probe.py").write_text(
            "import os, signal\n"
            "def test_kill_self(tmp_path):\n"
            "    (tmp_path / 'big').write_bytes(b'x' * 1024)\n"
            "    os.kill(os.getpid(), signal.SIGKILL)\n"
        )
        sandbox_tmp = tmp_path / "tmpdir"
        sandbox_tmp.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("TMPDIR", "PYTEST_ADDOPTS")}
        env["TMPDIR"] = str(sandbox_tmp)

        child = subprocess.Popen(
            [sys.executable, "-m", "pytest", "test_probe.py", "-q", "-p", "no:cacheprovider"],
            cwd=project,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        child.communicate(timeout=120)
        assert child.returncode == -signal.SIGKILL, "probe was supposed to die by SIGKILL"

        roots = list(sandbox_tmp.glob("pytest-of-*"))
        assert roots, "no basetemp was created — the probe proves nothing"
        leaked = [d for d in roots[0].glob("pytest-*") if d.is_dir() and not d.is_symlink()]
        assert leaked, "SIGKILL did not leak a basetemp — the premise changed; rewrite this test"
        lock = leaked[0] / ".lock"
        assert lock.exists(), "no .lock survived — the sweep's dead-pid path is untestable here"

        conftest = _conftest_module()
        removed = conftest._sweep_abandoned_pytest_basetemps(roots[0])

        assert removed >= 1
        assert not leaked[0].exists(), "the sweep did not reclaim a SIGKILLed run's basetemp"
