"""#4434: the per-test tmp_path bound must be SHOWN to bound, in bytes.

The measurement (2026-08-02): one unit+contracts run held 15.8 GB across
3,847 tmp_path dirs, largest 22 MB — not whales, every seeded-library test
held simultaneously until session end, because the reclaim mechanism was
wired only into perf/conftest.py. The fix hoists an outcome-aware reclaim
into tests/conftest.py: reclaim on pass, retain on failure, retention capped
in bytes and LOUD past the cap.

Per EPIC #4487, the mechanism claiming to bound disk is proven by MEASURING
BYTES after a real child pytest run that includes failures — not by
asserting "reclaim was called". A child session is run FROM THIS TREE (a
probe outside the rootdir would never load tests/conftest.py and the
assertion would pass while proving nothing — the mutation-found lesson in
test_conftest_temp_cleanup.py), against a dedicated --basetemp, and the
basetemp's total bytes are the assertion.

Also here: the dual-basetemp-location sweep (#4434's second half). pytest
roots its basetemp in $TMPDIR when exported and /tmp when not; the two
launch paths differ, so the startup sweep must cover BOTH or every run
cleans one tree while the other accumulates untouched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVER_ROOT = REPO_ROOT / "fichero-server"


def _root_conftest():
    """The ALREADY-LOADED tests/conftest.py, found by file path.

    Same technique and same reason as tests/perf/conftest.py: a bare
    ``import conftest`` resolves to whichever of the several conftest.py
    files pytest registered first, and re-executing the file doubles its
    module-level side effects (including the query-count middleware).
    """
    root_path = (Path(__file__).resolve().parents[1] / "conftest.py").resolve()
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) and Path(module.__file__).resolve() == root_path:
            return module
    raise RuntimeError("tests/conftest.py not loaded — expected before this file")


def _tree_bytes(root: Path) -> int:
    return sum(
        p.stat().st_size
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    )


def _run_probe(probe_source: str, basetemp: Path, extra_env: dict[str, str]) -> str:
    """Run a real child pytest session on a probe INSIDE this tree.

    The probe must live under fichero-server/tests/ or tests/conftest.py —
    the module under test — never loads. It is pid+uuid-suffixed and removed
    in ``finally`` so a killed run leaves at worst one stray file, never a
    collision.
    """
    probe_dir = (
        Path(__file__).resolve().parent / f"_bound_probe_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    )
    probe_dir.mkdir()
    try:
        (probe_dir / "test_probe.py").write_text(probe_source)
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("FICHERO_BASE_PATH", "PYTEST_ADDOPTS", "FICHERO_PERF_RATCHET")
        }
        env["PYTHONPATH"] = str(SERVER_ROOT / "src")
        env.update(extra_env)
        child = subprocess.run(
            [
                sys.executable, "-m", "pytest", str(probe_dir), "-q",
                "-p", "no:cacheprovider", f"--basetemp={basetemp}",
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        # Failures are part of the probe by design; anything else (collection
        # error, conftest crash) means the run proved nothing.
        assert child.returncode == 1, (
            f"probe expected exit 1 (tests failed by design), got "
            f"{child.returncode}:\n{child.stdout[-2000:]}\n{child.stderr[-2000:]}"
        )
        return child.stdout
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


PROBE_MB = 2
_PROBE_COMMON = f"""
def _seed(tmp_path):
    (tmp_path / "seeded.duckdb").write_bytes(b"x" * {PROBE_MB} * 1024 * 1024)
"""


class TestTheBoundHolds:
    """Measured bytes after a run with failures — the deliverable, not the fix."""

    @pytest.mark.slow
    def test_passers_reclaimed_failure_retained_bytes_bounded(self, tmp_path):
        basetemp = tmp_path / "bt"
        probe = _PROBE_COMMON + "".join(
            f"def test_pass_{i}(tmp_path):\n    _seed(tmp_path)\n" for i in range(5)
        ) + "def test_fail(tmp_path):\n    _seed(tmp_path)\n    assert False\n"

        stdout = _run_probe(probe, basetemp, {})

        total = _tree_bytes(basetemp)
        seeded = PROBE_MB * 1024 * 1024
        # 6 tests wrote 12 MB. The bound: only the ONE failure's dir survives.
        assert total < 2 * seeded, (
            f"bound did NOT hold: {total / 1e6:.1f} MB on disk after a run "
            f"that wrote {6 * seeded / 1e6:.0f} MB — passed tests' tmp dirs "
            "were not reclaimed"
        )
        assert total >= seeded, (
            f"only {total / 1e6:.1f} MB retained — the FAILING test's "
            "artifacts were reclaimed too; retention is the other half of "
            "the contract"
        )
        # Path-reuse trap (e767147e5): passers' numbered dirs must survive as
        # EMPTY stubs, keeping their numbered slots taken.
        # pytest also plants a `<name>current` convenience SYMLINK per test —
        # exclude those or the count doubles.
        pass_dirs = [
            d for d in basetemp.glob("test_pass_*")
            if d.is_dir() and not d.is_symlink()
        ]
        assert len(pass_dirs) == 5, f"expected 5 passer stub dirs, found {len(pass_dirs)}"
        for d in pass_dirs:
            assert list(d.iterdir()) == [], f"passer dir {d.name} not emptied"
        assert "retained 1 failing tests' tmp dirs" in stdout, (
            "the retention must be said out loud in the terminal summary"
        )

    @pytest.mark.slow
    def test_retention_cap_bounds_a_failure_storm_loudly(self, tmp_path):
        """Condition from the GO: 'keep failures' must itself be bounded, and
        hitting the cap must be loud, not a silent drop."""
        basetemp = tmp_path / "bt"
        probe = _PROBE_COMMON + "".join(
            f"def test_fail_{i}(tmp_path):\n    _seed(tmp_path)\n    assert False\n"
            for i in range(3)
        )
        cap = 3 * 1024 * 1024  # fits ONE 2 MB failure, not two

        stdout = _run_probe(
            probe, basetemp, {"FICHERO_TMP_RETAIN_CAP_BYTES": str(cap)}
        )

        total = _tree_bytes(basetemp)
        assert total <= cap, (
            f"cap did NOT hold: {total / 1e6:.1f} MB retained against a "
            f"{cap / 1e6:.1f} MB cap — an unbounded 'keep failures' is the "
            "same leak wearing a better justification"
        )
        assert total >= PROBE_MB * 1024 * 1024, (
            "the first failure under the cap must still be retained"
        )
        assert "RETENTION CAP HIT" in stdout, (
            "reclaiming past the cap must be announced, never silent"
        )


class TestSweepCoversBothBasetempLocations:
    """The second half of #4434: two locations, one sweeper, nothing forcing
    them to agree — until this."""

    def test_roots_include_both_tmpdir_and_slash_tmp(self, monkeypatch, tmp_path):
        conftest = _root_conftest()
        fake_tmpdir = tmp_path / "var-folders-T"
        fake_tmpdir.mkdir()
        monkeypatch.setattr(
            conftest._tempfile, "gettempdir", lambda: str(fake_tmpdir)
        )

        roots = conftest._pytest_basetemp_roots()

        resolved_parents = {r.parent for r in roots}
        assert fake_tmpdir.resolve() in resolved_parents, "missing $TMPDIR root"
        assert Path("/tmp").resolve() in resolved_parents, "missing /tmp root"
        assert len(roots) == 2

    def test_identical_locations_are_swept_once(self, monkeypatch):
        conftest = _root_conftest()
        monkeypatch.setattr(conftest._tempfile, "gettempdir", lambda: "/tmp")

        assert len(conftest._pytest_basetemp_roots()) == 1

    def test_default_sweep_reclaims_dead_runs_in_BOTH_roots(self, monkeypatch, tmp_path):
        """The wiring, end to end: root=None must visit every root, or the
        blindness this fixes is reintroduced one refactor from now."""
        conftest = _root_conftest()
        roots = []
        for name in ("loc-a", "loc-b"):
            base = tmp_path / name / "pytest-of-user"
            dead = base / "pytest-1"
            dead.mkdir(parents=True)
            (dead / "payload.duckdb").write_bytes(b"x")
            (dead / ".lock").write_text("999999999")
            old = 0.0
            os.utime(dead, (old, old))
            roots.append(base)
        monkeypatch.setattr(conftest, "_pytest_basetemp_roots", lambda: roots)

        removed = conftest._sweep_abandoned_pytest_basetemps()

        assert removed == 2, "a dead run in one of the two roots survived"
        for base in roots:
            assert not (base / "pytest-1").exists()
