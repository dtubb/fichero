"""The perf suite's live-disk-footprint fix (#4434 follow-up).

`tests/conftest.py`'s two sweeps stop DEAD runs from accumulating; neither
touches a single LIVE session, where every perf test seeds a full library
(images, DuckDB, LanceDB vectors) under its own `tmp_path` and nothing frees
it until the session ends. Observed 2026-08-01: 26 minutes into the perf
suite, 14 GB held simultaneously by tests that had already passed.

The obvious fix — `tmp_path_retention_policy="failed"` — is a trap already
hit once (`e767147e5`): pytest's own `tmp_path` teardown does an outright
`rmtree` of the numbered directory under that policy, which frees the
directory's NUMBERED SUFFIX for reuse (`make_numbered_dir` scans the
basetemp with `os.scandir` for "existing" numbers). A later test whose node
id truncates to the same 30-character prefix is then handed the SAME
absolute path, and a path-keyed process cache (`db_manager`,
`get_activity_tracker`) serves it a stale handle to a database that was
already deleted.

This proves, directly against pytest's own `TempPathFactory`, that emptying
a directory's CONTENTS (the fix in `reclaim_tmp_path_contents`) does NOT
trigger that reuse, while a full `rmtree` of the directory itself DOES —
so the mechanism this fix relies on is demonstrated, not assumed. No perf
test is run to prove this; the pytest machinery is exercised directly and
synthetically, per the instruction that started this work: reason it from
the fixtures, don't run the suite to find out.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from _pytest.tmpdir import TempPathFactory


def _reclaim_tmp_path_contents():
    """Reach ``tests/conftest.py``'s helper without a bare ``import conftest``.

    Several directories under ``tests/`` each have their own file literally
    named ``conftest.py`` (this one's parent, plus ``tests/unit/conftest.py``
    and others) — pytest's own loader disambiguates them internally, but a
    plain Python-level ``from conftest import ...`` does not: which file it
    resolves to depends on sys.path order and collection order, and it was
    observed to resolve to the WRONG one when this test file was collected
    alongside other suites, silently breaking the query-count ratchet's
    middleware for the rest of the session (found by running this file next
    to ``test_query_ratchet_workflow_endpoints.py`` — 0 queries recorded for
    an endpoint that plainly touches the DB). pytest loads
    ``tests/conftest.py`` before any test under ``tests/`` is collected, so
    find the module it already imported by file path instead of by name —
    the same technique ``tests/perf/conftest.py`` uses for the same reason.
    """
    root_path = (Path(__file__).resolve().parent.parent / "conftest.py").resolve()
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) and Path(module.__file__).resolve() == root_path:
            return module.reclaim_tmp_path_contents
    raise RuntimeError(f"tests/conftest.py not found in sys.modules — expected it loaded before {__file__}")


reclaim_tmp_path_contents = _reclaim_tmp_path_contents()


def _factory(basetemp: Path) -> TempPathFactory:
    return TempPathFactory(
        given_basetemp=basetemp,
        retention_count=1,
        retention_policy="all",
        trace=lambda *a, **k: None,
        _ispytest=True,
    )


class TestReclaimTmpPathContents:
    def test_empties_children_but_keeps_the_directory(self, tmp_path):
        (tmp_path / "library.duckdb").write_bytes(b"x" * 1024)
        sub = tmp_path / "package.fichero" / "lance"
        sub.mkdir(parents=True)
        (sub / "vectors.lance").write_bytes(b"y" * 1024)

        reclaim_tmp_path_contents(tmp_path)

        assert tmp_path.is_dir(), "the directory itself must survive"
        assert list(tmp_path.iterdir()) == [], "every child must be gone"

    def test_a_directory_already_empty_is_a_noop(self, tmp_path):
        reclaim_tmp_path_contents(tmp_path)  # must not raise
        assert tmp_path.is_dir()

    def test_a_permission_error_on_one_child_does_not_abort_the_rest(self, tmp_path, monkeypatch):
        """Best-effort, like pytest's own tmp_path teardown: one stubborn
        file must not leave the rest of a multi-GB seeded library
        unreclaimed, and must never fail an otherwise-passing test."""
        (tmp_path / "a.duckdb").write_bytes(b"x")
        (tmp_path / "b.duckdb").write_bytes(b"x")

        real_unlink = Path.unlink

        def flaky_unlink(self, *, missing_ok=False):
            if self.name == "a.duckdb":
                raise PermissionError("locked")
            return real_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", flaky_unlink)

        reclaim_tmp_path_contents(tmp_path)  # must not raise

        assert not (tmp_path / "b.duckdb").exists(), "the reachable file must still be reclaimed"


class TestNumberedDirectoryReuseIsTheRealTrap:
    """Prove, against pytest's own machinery, why content-only clearing is
    required rather than an outright `rmtree` of the numbered directory."""

    def test_full_rmtree_of_the_directory_reuses_its_number(self, tmp_path):
        factory = _factory(tmp_path.resolve())
        first = factory.mktemp("same_prefix", numbered=True)

        shutil.rmtree(first)
        second = factory.mktemp("same_prefix", numbered=True)

        assert second == first, (
            "this test documents the TRAP, not the fix: pytest's own "
            "make_numbered_dir reused the freed number here, which is "
            "exactly how e767147e5 handed a later test a stale path-keyed "
            "cache entry. If this assertion ever fails, pytest's directory "
            "numbering changed and the rationale in reclaim_tmp_path_contents "
            "needs re-verifying, not deleting."
        )

    def test_emptying_contents_never_reuses_the_number(self, tmp_path):
        factory = _factory(tmp_path.resolve())
        first = factory.mktemp("same_prefix", numbered=True)
        (first / "seeded_library.duckdb").write_bytes(b"x" * 4096)

        reclaim_tmp_path_contents(first)
        second = factory.mktemp("same_prefix", numbered=True)

        assert second != first, (
            "the directory must still be counted as taken by pytest's own "
            "numbered-directory scan, or this fix reintroduces the exact "
            "path-reuse defect it exists to avoid"
        )
        assert first.is_dir() and list(first.iterdir()) == [], (
            "the disk space must actually be reclaimed even though the "
            "numbered slot stays taken"
        )
