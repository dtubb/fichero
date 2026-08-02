"""
Shared pytest fixtures for all tests.

Provides fixtures for package documents testing with proper isolation.
"""

import asyncio
import faulthandler
import inspect
import os
import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock

# #4227 split fichero-cli/ and fichero-mcp/ out of the server package. Their
# tests still live in this tree, and every gate sets only
# PYTHONPATH=fichero-server/src — add the sibling products' src dirs here so
# one seam (this conftest) covers all pytest invocations.
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _sibling in ("fichero-cli/src", "fichero-mcp/src"):
    _sibling_path = str(_REPO_ROOT / _sibling)
    if _sibling_path not in sys.path:
        sys.path.insert(0, _sibling_path)

# #4487 gave every guardrail script `from _check_floor import ...`, which
# resolves only with scripts/ on sys.path. Contract tests spec-load those
# scripts in place, and whether that import worked depended on COLLECTION
# ORDER (a unit test module happening to add the path first) — contracts
# alone failed at collection while unit+contracts passed. One seam here,
# APPENDED so nothing in scripts/ can shadow a real package.
_scripts_path = str(_REPO_ROOT / "scripts")
if _scripts_path not in sys.path:
    sys.path.append(_scripts_path)

from fastapi.testclient import TestClient

# Keep existing route-heavy tests running against the broader dev API surface.
os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
# Tests assume a clean library by default — disable automatic preset seeding
# so assertions like "GET /workflows returns []" keep working.
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
# #742 added shared-secret auth + a loopback check. FastAPI's TestClient
# uses host "testclient" (not 127.0.0.1) and doesn't carry the Authorization
# header tests aren't aware of. Disable auth entirely for the test app —
# every prior route test predates the auth feature and asserts on
# response shape, not auth.
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")
# Local CI may run with a fastembed build whose Python TextEmbedding catalog
# does not include the production default BAAI/bge-m3 yet. Real-model tests use
# the prior supported model unless a verifier explicitly overrides it.
os.environ.setdefault("FICHERO_EMBED_MODEL", "intfloat/multilingual-e5-large")
# #2235: fail loudly if any unregistered type crosses the LangGraph msgpack
# boundary (today just warns; future versions will hard-block).
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

# Tests that create bare TestClient(app) (e.g. test_api_providers.py:16,
# test_providers.py's per-class fixtures) bypass the conftest `client` /
# `app_db` fixtures and hit `settings.app_db_path` directly — which is
# ~/Library/Application Support/com.fichero.fichero/app.duckdb in prod
# and fights the running uvicorn for the exclusive duckdb lock. Override
# `FICHERO_BASE_PATH` (consumed by pydantic-settings env_prefix="FICHERO_")
# so app_db_path resolves under a per-process tmp dir.
import atexit as _atexit
import shutil as _shutil
import tempfile as _tempfile
import pathlib as _pathlib
from urllib.parse import quote

_TEST_BASE_PREFIX = "fichero-tests-"


def _pid_is_alive(pid: int) -> bool:
    """True when a process with this pid exists.

    PID reuse can make a dead run's directory look live, so this errs toward
    "alive" — under-cleaning is safe, deleting a running suite's database is
    not.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return True
    return True


def _sweep_abandoned_test_base_paths() -> int:
    """Remove base dirs left by runs whose process is gone (#4228).

    Each run creates ``fichero-tests-<pid>-*`` and, until this, never removed
    it. Four days of runs had accumulated 705 directories and 3.5 GB, which
    exhausted the disk and produced ~45 SETUP errors in a full suite — fixtures
    failing before any test body ran. Re-running to diagnose the instability
    consumed more disk and made the next run likelier to die.

    The finalizer below handles a normal exit, but EVERY failed run that day
    ended in a kill, where no finalizer fires. So the durable half is this
    sweep: on startup, remove directories whose owning pid no longer exists.
    A live run's directory is never touched — its pid is alive by definition.
    """
    removed = 0
    tmp_root = _pathlib.Path(_tempfile.gettempdir())
    for entry in tmp_root.glob(f"{_TEST_BASE_PREFIX}*"):
        if not entry.is_dir():
            continue
        suffix = entry.name[len(_TEST_BASE_PREFIX) :]
        pid_text = suffix.split("-", 1)[0]
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid == os.getpid() or _pid_is_alive(pid):
            continue
        _shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    return removed


def _pytest_basetemp_roots() -> list[_pathlib.Path]:
    """EVERY place pytest may keep its numbered basetemps (``pytest-of-<user>``).

    There are TWO, and which one a run uses depends on how it was launched
    (#4434, observed 2026-08-02): pytest derives its basetemp from
    ``tempfile.gettempdir()``, which honours ``$TMPDIR`` when exported (macOS
    login shells: ``/var/folders/.../T/``) and falls back to ``/tmp`` when not
    (some spawned/managed contexts). A sweeper that checks only the location
    the CURRENT process resolves to cleans one tree while the other
    accumulates untouched — 6.4 GB sat in ``/private/tmp`` while
    ``$TMPDIR``'s tree was empty, and during the gate it was the inverse.
    Two locations, one sweeper, nothing forcing them to agree.

    Sweeping both is chosen over forcing a single ``TMPDIR``: forcing means
    editing every launch path (gate, bare pytest, Xcode-spawned, subagents)
    and any missed one silently recreates the blindness; this is one function.
    """
    import getpass

    try:
        user = getpass.getuser()
    except Exception:  # no passwd entry (some CI sandboxes)
        user = os.environ.get("USER", "unknown")
    roots: list[_pathlib.Path] = []
    seen: set[_pathlib.Path] = set()
    for candidate in (_pathlib.Path(_tempfile.gettempdir()), _pathlib.Path("/tmp")):
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue  # TMPDIR unset → gettempdir() IS /tmp; sweep it once
        seen.add(resolved)
        roots.append(resolved / f"pytest-of-{user}")
    return roots


def _safe_mtime(path: _pathlib.Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _sweep_abandoned_pytest_basetemps(
    root: _pathlib.Path | None = None,
    *,
    keep_lockless: int = 1,
    min_lockless_age_s: float = 60.0,
) -> int:
    """Remove leaked pytest basetemps (``pytest-of-<user>/pytest-N``) (#4434).

    This is the OTHER temp tree — the #4228 sweep above covers only
    ``fichero-tests-<pid>-*``. The 77 GB that filled the disk on 2026-07-30
    was nineteen ~4 GB ``pytest-N`` run directories (seeded libraries, DuckDB
    files, vectors) created by ``tmp_path``/``tmp_path_factory``, which this
    conftest never swept and pytest's own retention could not save:

    * A KILLED run (the gate watchdog escalates to SIGKILL after 1s) never
      reaches session cleanup, so its dir survives WITH its ``.lock``, and
      pytest's collector ignores locked dirs for a further hour — an intensive
      session accumulates them faster than they age out.
    * A FINISHED run removes its lock but the dir is retained by count.

    Policy (Daniel, #4434): a passing run leaves nothing, a failing run may
    keep ONE (most recent), a killed run cannot leak. Enforced here as:

    * ``.lock`` naming a LIVE pid → never touched (a concurrent lane's run).
    * ``.lock`` naming a dead pid → removed NOW (killed run cannot leak).
    * lockless (finished) → newest ``keep_lockless`` kept, older removed
      (``tmp_path_retention_count=1`` bounds what pytest itself retains; the
      retention POLICY stays "all" — see pyproject.toml for why "failed"
      breaks path-keyed caches via tmp-dir name reuse).
    * lockless dirs younger than ``min_lockless_age_s`` are skipped: pytest
      creates the dir a moment before writing its lock, and a starting
      concurrent run must not lose that race.
    """
    if root is None:
        # Sweep BOTH possible locations — see _pytest_basetemp_roots.
        return sum(
            _sweep_abandoned_pytest_basetemps(
                r,
                keep_lockless=keep_lockless,
                min_lockless_age_s=min_lockless_age_s,
            )
            for r in _pytest_basetemp_roots()
        )
    removed = 0
    base = root
    if not base.is_dir():
        return 0
    import time as _time

    now = _time.time()
    lockless: list[_pathlib.Path] = []
    for entry in base.glob("pytest-*"):
        if entry.is_symlink() or not entry.is_dir():
            continue  # the 'current' convenience symlink, stray files
        lock = entry / ".lock"
        if lock.exists():
            try:
                pid = int(lock.read_text().strip() or "0")
            except (OSError, ValueError):
                pid = 0
            if pid and (pid == os.getpid() or _pid_is_alive(pid)):
                continue  # live run — deleting it is the one outcome worse than leaking
            _shutil.rmtree(entry, ignore_errors=True)
            removed += 1
        elif now - _safe_mtime(entry) >= min_lockless_age_s:
            lockless.append(entry)
    lockless.sort(key=_safe_mtime, reverse=True)
    for entry in lockless[keep_lockless:]:
        _shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    return removed


def reclaim_tmp_path_contents(path: _pathlib.Path) -> None:
    """Empty every child of ``path`` without removing ``path`` itself (#4434).

    The two sweeps above stop DEAD runs from accumulating. They do nothing
    for a single LIVE session: a suite whose tests each seed a full library
    (images, DuckDB, LanceDB vectors) under their own ``tmp_path`` holds
    EVERY passed test's copy simultaneously until session end, because
    nothing in pytest's own retention machinery frees a passing test's
    directory mid-run — ``tmp_path_retention_count``/``_policy`` only prune
    OLD SESSIONS' basetemps. Observed 2026-08-01: 26 minutes into the perf
    suite, 14 GB held by tests that had already passed.

    ``tmp_path_retention_policy="failed"`` looks like the fix and ISN'T:
    pytest's own ``tmp_path`` fixture teardown (``_pytest/tmpdir.py``) does
    exactly a directory ``rmtree`` under that policy, and
    ``make_numbered_dir`` (``_pytest/pathlib.py``) computes the next numbered
    suffix by scanning the basetemp with ``os.scandir`` — so removing a
    numbered directory ENTIRELY frees its number for reuse. A later test
    whose node id truncates to the same 30-character prefix (`_mk_tmp`'s
    ``name[:30]``) is then handed the SAME absolute path, and every
    path-keyed process cache (``db_manager``, ``get_activity_tracker``)
    serves a stale handle to a database that no longer exists — the exact
    "Table workflow_runs does not exist" incident in ``e767147e5``.

    This reclaims the disk WITHOUT that trap: it empties the directory's
    CONTENTS and leaves the (now-empty) directory itself in place.
    ``find_prefixed`` (the function ``make_numbered_dir`` uses to find
    "existing" numbers) lists whatever still EXISTS via ``os.scandir`` —
    an empty stub with the same name keeps its numbered slot, so it can
    never be handed to a later test. Verified synthetically against
    pytest's own ``TempPathFactory`` in
    ``tests/unit/test_perf_disk_reclaim.py`` (a full ``rmtree`` of the
    directory DOES reuse the number; emptying contents does NOT).

    Caller is responsible for calling this only after every fixture holding
    an open connection into ``path`` has already closed it — this function
    does not know what created the files it is deleting.

    Best-effort, like the two sweeps above and like pytest's own ``rmtree``
    in ``_pytest/tmpdir.py``: a leaked file handle or a permissions quirk on
    one child must not abort reclaiming the rest of a multi-GB seeded
    library, and must never be allowed to fail a passing test at teardown.
    """
    for child in path.iterdir():
        if child.is_dir():
            _shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Per-test tmp_path reclaim, ALL suites (#4434)
# ---------------------------------------------------------------------------
# The measurement (2026-08-02, issue #4434): one unit+contracts run held
# 15.8 GB across 3,847 tmp_path dirs, largest 22 MB — 96% of the mass in
# ~3,000 dirs of 1-10 MB each. Not whales; every seeded-library test, held
# simultaneously until session end. The reclaim mechanism existed and worked,
# but was wired only into perf/conftest.py — a bound that runs on one branch
# of the suite while reading as if it covers the whole (the #4485 shape).
#
# Policy: reclaim a PASSED test's tmp_path at teardown; RETAIN a failed
# test's (that is the data you want) — but bounded: retention is capped in
# BYTES, first-retained kept, and once the cap is hit further failures are
# reclaimed LOUDLY (listed in the terminal summary). An unbounded "keep
# failures" is the same leak wearing a better justification: 500 failures
# x 10 MB is 5 GB, and a bad day produces exactly that.

# 1 GiB ≈ 45+ retained failures at the observed 22 MB max. Env-overridable so
# the bound-holds test can exercise the cap path with kilobytes, not gigabytes.
_RETAIN_FAILED_TMP_BYTES_CAP = int(
    os.environ.get("FICHERO_TMP_RETAIN_CAP_BYTES", str(1 * 1024**3))
)
_retained_failed_tmp: list[tuple[str, str, int]] = []  # (nodeid, path, bytes)
_overcap_reclaimed_tmp: list[str] = []


def _dir_bytes(path: _pathlib.Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file() and not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa: ARG001
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        item._fichero_tmp_retain = True  # any phase failing marks the test


@pytest.fixture(autouse=True)
def _reclaim_tmp_path_after_test(request, tmp_path):
    """Reclaim tmp_path on pass, retain (bounded) on failure — every suite.

    Requesting only ``tmp_path`` keeps this autouse fixture's setup EARLY
    relative to the test's own fixtures, so per pytest's LIFO teardown order
    it runs LAST — after ``test_package``'s ``db_manager.close_all()`` and
    ``app_db``'s ``db.close()`` have released every connection into this
    directory (same technique, same reason as perf/conftest.py's fixture,
    which keeps its own unconditional reclaim: multi-GB perf dirs are never
    worth retaining).

    Contents are EMPTIED, never the directory removed — see
    ``reclaim_tmp_path_contents`` for the numbered-dir path-reuse trap.
    """
    yield
    if getattr(request.node, "_fichero_tmp_retain", False):
        size = _dir_bytes(tmp_path)
        held = sum(b for _, _, b in _retained_failed_tmp)
        if held + size <= _RETAIN_FAILED_TMP_BYTES_CAP:
            _retained_failed_tmp.append((request.node.nodeid, str(tmp_path), size))
            return
        # Cap hit: reclaim anyway, but never silently — the summary names it.
        _overcap_reclaimed_tmp.append(
            f"{request.node.nodeid} ({size / 1e6:.1f} MB)"
        )
    reclaim_tmp_path_contents(tmp_path)


def _make_test_base_path() -> _pathlib.Path:
    """Create a per-process base path for test-only app storage.

    Concurrent verifier runs must never point at the same DuckDB path,
    or they can deadlock on the exclusive database lock.
    """

    return _pathlib.Path(
        _tempfile.mkdtemp(prefix=f"{_TEST_BASE_PREFIX}{os.getpid()}-")
    )


_sweep_abandoned_test_base_paths()
_sweep_abandoned_pytest_basetemps()
_test_base = _make_test_base_path()
os.environ.setdefault("FICHERO_BASE_PATH", str(_test_base))
# Normal-exit cleanup. Cannot fire on SIGKILL, which is why the startup sweep
# above exists as the durable half rather than the belt-and-braces one.
_atexit.register(_shutil.rmtree, _test_base, True)

from fichero_server.api.main import app  # noqa: E402
from fichero_server.db import db_manager  # noqa: E402
from fichero_server.db.app import AppDatabase  # noqa: E402

_deadlock_dump_armed = False


def _deadlock_dump_timeout_seconds() -> float | None:
    """Opt-in session hang dump timeout for deadlock triage (#2651)."""
    raw = os.environ.get("FICHERO_TEST_DEADLOCK_TIMEOUT", "").strip()
    if not raw:
        return None
    try:
        timeout = float(raw)
    except ValueError:
        return None
    if timeout <= 0:
        return None
    return timeout


def pytest_sessionstart(session):  # noqa: ARG001
    """Optionally arm faulthandler to dump all Python stacks on a hung suite."""
    global _deadlock_dump_armed

    if _ratchet_enabled():
        _verify_query_counting_wired()

    timeout = _deadlock_dump_timeout_seconds()
    if timeout is None:
        _deadlock_dump_armed = False
        return
    if not faulthandler.is_enabled():
        faulthandler.enable(all_threads=True)
    faulthandler.dump_traceback_later(timeout, repeat=False)
    _deadlock_dump_armed = True


# NOTE: pytest_sessionfinish is defined ONCE, far below (the perf-ratchet
# section) — it also cancels the faulthandler hang-dump alarm. A second def
# here would silently SHADOW it (module attribute, last def wins), which is
# exactly what happened until 2026-08-02: the cancel hook was dead code and
# test_pytest_sessionfinish_cancels_only_when_armed failed against the
# ratchet's def. One hook name, one def.


# NOTE: pytest_collection_modifyitems is defined ONCE, below the Apple
# probes — an earlier duplicate def silently shadowed the anyio automark
# (module attribute, last def wins), which broke every async-FIXTURE test
# (pytest_pyfunc_call covers coroutine TESTS, not their fixtures): the 20
# test_background_tasks errors on 2026-08-02. Same defect and same fix as
# pytest_sessionfinish. One hook name, one def.


# ---------------------------------------------------------------------------
# Apple Vision / Apple Intelligence skip markers (#840 follow-up)
#
# Tests marked @pytest.mark.requires_apple_vision exercise the real macOS
# Vision framework. Auto-skipped when:
#   - Not on macOS (sys.platform != "darwin")
#   - PyObjC's Quartz/Vision modules can't import
#
# Tests marked @pytest.mark.requires_apple_intelligence exercise the
# bundled fm-bridge against on-device Foundation Models. Auto-skipped when:
#   - Not on macOS
#   - fm-bridge binary isn't present
#   - fm-bridge --probe returns non-available (older OS, unsupported chip,
#     Apple Intelligence not opted-in)
# ---------------------------------------------------------------------------


def _apple_vision_available() -> bool:
    import sys
    if sys.platform != "darwin":
        return False
    try:
        import Quartz  # noqa: F401
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


def _apple_intelligence_available() -> bool:
    import sys
    import json
    import subprocess
    from pathlib import Path
    if sys.platform != "darwin":
        return False
    # Mirror the binary lookup in fichero_server.llm._apple_intelligence_chat.
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "fichero-server" / "src" / "fichero_server"
        / "resources" / "bin" / "fm-bridge",
        repo_root / "fichero-server" / "bin" / "fm-bridge" / "fm-bridge",
    ]
    binary = next(
        (p for p in candidates if p.is_file() and p.stat().st_mode & 0o111),
        None,
    )
    if binary is None:
        return False
    try:
        result = subprocess.run(
            [str(binary), "--probe"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout.decode())
    except json.JSONDecodeError:
        return False
    return bool(payload.get("available"))


# Compute once at collection time — both probes are deterministic for
# the duration of a test session and cheap (Vision: import-only,
# Intelligence: ~50ms subprocess).
_APPLE_VISION_OK = _apple_vision_available()
_APPLE_INTELLIGENCE_OK = _apple_intelligence_available()


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """The ONE collection hook: anyio automark, Apple skips, known-spec xfails.

    These lived as THREE separate defs of this hook name; only the last one
    executed (module attribute, last def wins), so the anyio automark and the
    Apple skips were silently dead — async-fixture tests errored and nobody
    connected it to a shadowed hook. Merged 2026-08-02; do not split again.
    """
    skip_vision = pytest.mark.skip(
        reason="Apple Vision unavailable (non-mac or PyObjC Vision missing)"
    )
    skip_intelligence = pytest.mark.skip(
        reason="Apple Intelligence unavailable (probe failed; needs macOS 26+ "
               "on Apple Silicon with AI opted in)"
    )
    for item in items:
        test_obj = getattr(item, "obj", None)
        if test_obj is not None and inspect.iscoroutinefunction(test_obj):
            item.add_marker(pytest.mark.anyio)
        if "requires_apple_vision" in item.keywords and not _APPLE_VISION_OK:
            item.add_marker(skip_vision)
        if (
            "requires_apple_intelligence" in item.keywords
            and not _APPLE_INTELLIGENCE_OK
        ):
            item.add_marker(skip_intelligence)

    # Known specification failures (#4382 #4395 #4420): xfail(strict=True)
    # on the listed tests, and only those. Marking a whole module also marks
    # the tests in it that pass, and strict mode then fails those FOR
    # PASSING — so the unit is one test id. Strict is the point: when the
    # defect is fixed the test passes, this turns that into a failure, and
    # the failure says to delete the line.
    known = _known_specification_failures()
    if not known:
        return
    prefix = "fichero-server/"
    for item in items:
        nodeid = item.nodeid
        if nodeid.startswith(prefix):
            nodeid = nodeid[len(prefix):]
        if nodeid in known:
            item.add_marker(
                pytest.mark.xfail(
                    strict=True,
                    reason=f"specified, not yet implemented — see {_SPEC_FAILURES_PATH.name}",
                )
            )


def pytest_pyfunc_call(pyfuncitem):
    """
    Fallback async test runner for suites using `@pytest.mark.asyncio`
    without pytest-asyncio installed.
    """
    test_obj = getattr(pyfuncitem, "obj", None)
    if test_obj is not None and inspect.iscoroutinefunction(test_obj):
        kwargs = {
            name: pyfuncitem.funcargs[name]
            for name in pyfuncitem._fixtureinfo.argnames
            if name in pyfuncitem.funcargs
        }
        asyncio.run(test_obj(**kwargs))
        return True
    return None


@pytest.fixture
def app_db(tmp_path):
    """
    Create a test app-wide database for provider storage.

    This is separate from package databases and stores app-wide providers.

    Also swaps the module-level `_app_db` singleton used by routes that
    call `get_app_db()` directly (settings.py, parts of providers.py and
    chat.py) — without this swap those routes still open the prod
    ~/Library/Application Support/com.fichero.fichero/app.duckdb and
    fight the running uvicorn for the exclusive duckdb lock.
    """
    app_db_path = tmp_path / "test_app.duckdb"
    db = AppDatabase(path=app_db_path)

    import fichero_server.db.app as _app_db_module
    saved_singleton = _app_db_module._app_db
    _app_db_module._app_db = db

    yield db

    # Restore the prior singleton (likely None) so test isolation is
    # preserved across the session.
    _app_db_module._app_db = saved_singleton
    db.close()


@pytest.fixture
def test_package(tmp_path):
    """
    Create a test .fichero package with proper directory structure.

    This fixture creates a temporary package that mimics the real .fichero structure:
    - fichero.duckdb (database)
    - lance/ (vector storage)
    - storage/ (thumbnails, display images)
    - files/ (imported files for COPY mode)
    """
    # Create package directory
    package_path = tmp_path / "test.fichero"
    package_path.mkdir()

    # Create required subdirectories
    (package_path / "lance").mkdir()
    (package_path / "storage").mkdir()
    (package_path / "files").mkdir()

    # Initialize database for this package
    db_manager.get_database(package_path)

    yield package_path

    # Cleanup
    db_manager.close_all()


@pytest.fixture
def client(test_package, app_db):
    """
    Create test client with proper X-Fichero-Library-Path header.

    This client automatically includes the library path header in all requests,
    so tests can make requests without needing to manually add headers.

    Also overrides the app database dependency to use the test app_db
    and the library database dependency to use the test package db.
    """
    from fichero_server.api.main import get_library_database, get_library_database_for_write
    from fichero_server.api.routes.entity.entities import _digest_library_database
    from fichero_server.api.routes.ai.providers import get_app_database

    # Override dependencies to use test dbs
    app.dependency_overrides[get_app_database] = lambda: app_db
    app.dependency_overrides[_digest_library_database] = (
        lambda: db_manager.get_database(test_package)
    )
    app.dependency_overrides[get_library_database] = lambda: db_manager.get_database(test_package)
    app.dependency_overrides[get_library_database_for_write] = lambda: db_manager.get_database(test_package)

    # Create client with default headers
    client = TestClient(
        app,
        headers={"X-Fichero-Library-Path": quote(str(test_package), safe="/")}
    )

    yield client

    # Cleanup: remove overrides
    app.dependency_overrides.clear()


@pytest.fixture
def db(test_package):
    """
    Get the Database instance for the test package.

    Use this fixture when tests need direct database access
    (e.g., to set up test data before making API requests).
    """
    return db_manager.get_database(test_package)


@pytest.fixture
def mock_db(monkeypatch):
    """
    Mock package database used by API route tests.

    Patches db_manager.get_database() so route dependency injection
    resolves to a controllable MagicMock instance.
    """
    mock = MagicMock()
    monkeypatch.setattr(db_manager, "get_database", lambda _path: mock)
    return mock


# =============================================================================
# fichero_server.api.main pollution guard (#4243)
# =============================================================================
# Several suites `importlib.reload(fichero_server.api.main)` with auth env flipped to
# test postures. When a restore path is missing (posture_parity), or restores
# under the WRONG env (device_pairing_e2e reloads "back" while monkeypatch's
# FICHERO_MULTIUSER=1 is still set), the process keeps an app whose middleware
# differs from the suite default — and every later TestClient 401s. 26 tests
# failed order-dependently in the full run; all green standalone.
#
# This guard notices the drift after each module and rebuilds the module under
# the suite-default env, turning silent cross-suite pollution into a bounded,
# local repair. Middleware COUNT is the signal because it is what breaks auth;
# a same-count reload is harmless churn and left alone.

_API_MAIN_BASELINE_MW: list[int] = []
_API_MAIN_AUTH_ENV = (
    "FICHERO_MULTIUSER",
    "FICHERO_TLS_SPKI_HASH",
    "FICHERO_TAILNET_URL",
)


def _restore_api_main_defaults() -> None:
    """Reload fichero_server.api.main under the suite-default auth env."""
    import importlib
    import sys

    module = sys.modules.get("fichero_server.api.main")
    if module is None:
        return
    saved = {k: os.environ.get(k) for k in ("FICHERO_DISABLE_AUTH", *_API_MAIN_AUTH_ENV)}
    os.environ["FICHERO_DISABLE_AUTH"] = "1"
    for key in _API_MAIN_AUTH_ENV:
        os.environ.pop(key, None)
    try:
        importlib.reload(module)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(autouse=True, scope="module")
def _api_main_pollution_guard():
    yield
    import sys

    module = sys.modules.get("fichero_server.api.main")
    app = getattr(module, "app", None) if module else None
    if app is None:
        return
    count = len(getattr(app, "user_middleware", []))
    if not _API_MAIN_BASELINE_MW:
        # Lazy baseline: the first module to touch api.main under the suite
        # default env defines "healthy". ponytail: if that first module were
        # itself a polluter the baseline would be wrong — today's first is
        # integration/test_action_library (clean, mw=3).
        _API_MAIN_BASELINE_MW.append(count)
        return
    if count != _API_MAIN_BASELINE_MW[0]:
        _restore_api_main_defaults()


# ---------------------------------------------------------------------------
# Performance ratchet: every test is timed (#4439) and the run is weighed (#4440)
# ---------------------------------------------------------------------------
#
# Not a separate suite you remember to run — a property of whatever you already
# ran. Slow down a query and the tests covering it say so on the next run,
# rather than waiting for the perf leg.
#
# Time is per test. Memory is per SESSION, because peak RSS is a property of the
# process and charging it to whichever test happened to be running is a number
# that means something else entirely — see perf_ratchet.py.
#
# Off by default: opt in with FICHERO_PERF_RATCHET=1 (the gate sets it). A
# developer running one test file on a laptop with a browser open should not be
# writing bars that everyone else then has to meet.

import os as _os  # noqa: E402
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent))


def _ratchet_enabled() -> bool:
    return _os.environ.get("FICHERO_PERF_RATCHET") == "1"


def _ratchet_scope(session) -> str:
    """The identity of WHAT was run, for the session-level memory bar (#4440).

    One test file and the whole suite have genuinely different peaks. Sharing a
    bar between them means the narrow run tightens it to a number the full suite
    can never meet, and the ratchet becomes a thing people switch off. So the
    invocation's paths ARE part of the measurement's name.
    """
    root = _Path(str(session.config.rootpath))
    parts = []
    for arg in session.config.args:
        raw = _Path(str(arg).split("::")[0])
        try:
            parts.append(str(raw.resolve().relative_to(root)))
        except (ValueError, OSError):
            parts.append(raw.name or str(raw))
    return ",".join(sorted(set(parts))) or "."


def pytest_runtest_logreport(report):
    """Record the call phase of each passing test."""
    if not _ratchet_enabled() or report.when != "call" or not report.passed:
        return
    import perf_ratchet

    perf_ratchet.note_test_duration(report.nodeid, report.duration)
    perf_ratchet.note_test_memory(report.nodeid)


# ---------------------------------------------------------------------------
# Query-count ratchet: every request is counted, held EXACTLY (#4443)
# ---------------------------------------------------------------------------
#
# The same idea as the timing ratchet above, and the same opt-in
# (FICHERO_PERF_RATCHET=1) — no test names itself, any test that exercises an
# endpoint through `client`/TestClient contributes its count automatically.
#
# A rise IS the diagnosis, not a hint: a timing says "this got slower" and
# leaves you to find out why; a count says "this endpoint went from 3 queries
# to 47" — the answer, not a symptom. It is also held EXACTLY, with no
# TOLERANCE and no NOISE_FLOOR (see perf_ratchet.flush_query_session): a query
# count does not care that the machine was busy.

_QUERY_RATCHET_BLIND_EXITCODE = 4


@app.middleware("http")
async def _count_queries_per_request(request, call_next):
    """Hold each endpoint's SQL query count to its best-ever, exactly."""
    if not _ratchet_enabled():
        return await call_next(request)

    from fichero_server.core.duckdb_session import get_query_count, reset_query_count

    reset_query_count()
    response = await call_next(request)
    # Populated by Starlette's router once the request has been matched; None
    # for a 404 with no matching route, which has nothing to ratchet.
    route = request.scope.get("route")
    if route is not None:
        import perf_ratchet

        perf_ratchet.note_query_count(
            f"queries.{request.method}.{route.path}", get_query_count()
        )
    return response


def _verify_query_counting_wired() -> None:
    """The counter itself must work, or "0 regressions" this session is a lie.

    A guardrail must know when it has gone blind (AGENTS.md rule 0): the
    dangerous failure isn't a missing baseline, it's a counting mechanism that
    silently stopped counting. Every request would then report 0 queries,
    every endpoint would "tighten" to 0, and the ratchet would pass forever
    while catching nothing — indistinguishable from a genuinely clean run. So
    before trusting anything this session records, prove the wrap in
    `duckdb_session.connect_utc` still counts one known query, and abort with
    a DISTINCT exit code (not the regression one) if it does not.
    """
    from fichero_server.core.duckdb_session import self_test_counting

    if self_test_counting() < 1:
        pytest.exit(
            "Query-count ratchet is BLIND: a known SELECT was not counted. "
            "The wrap in fichero_server.core.duckdb_session.connect_utc is "
            "broken — fix it before trusting any '0 regressions' from this "
            "run. This is a distinct exit code because 'I could not count' "
            "is not the same claim as 'no regression'.",
            returncode=_QUERY_RATCHET_BLIND_EXITCODE,
        )


def pytest_sessionfinish(session, exitstatus):
    """Compare everything once, tighten what improved, report what regressed.

    Also cancels the #2651 hang-dump alarm — this is the ONLY sessionfinish
    def in the module (a second one earlier in the file silently shadowed
    whichever came first; see the note beside pytest_sessionstart).
    """
    global _deadlock_dump_armed

    if _deadlock_dump_armed:
        faulthandler.cancel_dump_traceback_later()
        _deadlock_dump_armed = False

    if not _ratchet_enabled():
        return
    import perf_ratchet

    regressions = list(perf_ratchet.flush_session())
    query_regressions = list(perf_ratchet.flush_query_session())
    mem_regressions, mem_status = perf_ratchet.flush_session_memory(
        _ratchet_scope(session)
    )
    regressions = regressions + list(mem_regressions)
    blind = mem_status.startswith("blind:")
    if not regressions and not query_regressions and not blind:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None and regressions:
        reporter.write_sep("=", "PERFORMANCE REGRESSIONS", red=True)
        for line in regressions:
            reporter.write_line(f"  {line}")
        if regressions:
            reporter.write_line("")
            reporter.write_line(
                "  Each is slower or heavier than its own best-ever result. Fichero is"
            )
            reporter.write_line(
                "  meant to get faster and lighter, so a worse run is a decision: re-run"
            )
            reporter.write_line(
                "  on a quiet machine, or raise the entry in tests/perf_baseline.json and"
            )
            reporter.write_line("  say what bought the time or the memory.")
        for line in query_regressions:
            reporter.write_line(f"  {line}")
        if query_regressions:
            reporter.write_line("")
            reporter.write_line(
                "  Each endpoint issued more SQL queries than its own best-ever run —"
            )
            reporter.write_line(
                "  held EXACTLY, since a query count does not vary with machine load."
            )
            reporter.write_line(
                "  Usually an N+1: a loop issuing one query per row instead of one total."
            )
            reporter.write_line(
                "  If accepted, raise the entry in tests/perf_baseline.json and say why."
            )
    if reporter is not None and blind:
        reporter.write_sep("=", "MEMORY RATCHET WENT BLIND", red=True)
        reporter.write_line(f"  {mem_status}")
        reporter.write_line("")
        reporter.write_line(
            "  This is NOT a pass. Nothing was measured, so nothing was checked, and"
        )
        reporter.write_line(
            "  a guardrail that cannot measure keeps printing green from the day it"
        )
        reporter.write_line("  breaks. Fix the measurement before trusting the run.")

    # Exit code 3 = "tests passed, performance did not."
    # Exit code 4 = "tests passed, and the memory ratchet could not look at all."
    # Three answers, three codes: a regression needs a fix, blindness needs the
    # instrument repaired, and neither may be mistaken for the other or for a
    # test failure.
    if exitstatus == 0:
        session.exitstatus = 3 if (regressions or query_regressions) else 4


# ---------------------------------------------------------------------------
# Known specification failures (#4382 #4395 #4420)
# ---------------------------------------------------------------------------

_SPEC_FAILURES_PATH = _Path(__file__).resolve().parent / "known_specification_failures.txt"


def _known_specification_failures() -> set[str]:
    if not _SPEC_FAILURES_PATH.exists():
        return set()
    return {
        line.strip()
        for line in _SPEC_FAILURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


# The known-specification xfail marking lives in the single
# pytest_collection_modifyitems def above the Apple probes — a third def of
# the hook here was the one that shadowed the other two (see the note there).


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Say it out loud, every run.

    An xfail is silent by design — a dot in the output. That makes a known
    defect indistinguishable from no defect, which is the failure mode this
    project keeps hitting. So the count and its issues are printed at the end
    of EVERY run, in red, whether or not anything failed.
    """
    # #4434: retained failing tests' tmp dirs, and any dropped past the cap.
    if _retained_failed_tmp:
        held = sum(b for _, _, b in _retained_failed_tmp)
        terminalreporter.write_line(
            f"retained {len(_retained_failed_tmp)} failing tests' tmp dirs "
            f"({held / 1e6:.1f} MB, cap {_RETAIN_FAILED_TMP_BYTES_CAP / 1e9:.1f} GB, #4434):"
        )
        for nodeid, path, size in _retained_failed_tmp[:20]:
            terminalreporter.write_line(f"  {size / 1e6:8.1f} MB  {nodeid}  {path}")
        if len(_retained_failed_tmp) > 20:
            terminalreporter.write_line(
                f"  ... and {len(_retained_failed_tmp) - 20} more"
            )
    if _overcap_reclaimed_tmp:
        terminalreporter.write_sep(
            "=", "FAILING-TEST TMP RETENTION CAP HIT (#4434)", red=True
        )
        terminalreporter.write_line(
            f"  The {_RETAIN_FAILED_TMP_BYTES_CAP / 1e9:.1f} GB retention cap filled; "
            f"{len(_overcap_reclaimed_tmp)} later failures' tmp dirs were "
            "reclaimed anyway. Their artifacts are GONE — re-run those tests "
            "alone if you need the dirs. This is said out loud because "
            "silently dropping evidence is how a bound becomes a lie."
        )
        for line in _overcap_reclaimed_tmp[:20]:
            terminalreporter.write_line(f"    {line}")
        if len(_overcap_reclaimed_tmp) > 20:
            terminalreporter.write_line(
                f"    ... and {len(_overcap_reclaimed_tmp) - 20} more"
            )

    # #4434: a failing run's basetemp survives until the next run's sweep —
    # say WHERE, so nobody has to hunt /var/folders under time pressure.
    if exitstatus:
        try:
            basetemp = config._tmp_path_factory.getbasetemp()  # noqa: SLF001
        except Exception:
            basetemp = None
        if basetemp is not None:
            terminalreporter.write_line(
                f"retained failing-run temp dir (newest kept, older swept next "
                f"run, #4434): {basetemp}"
            )

    known = _known_specification_failures()
    if not known:
        return
    issues = sorted({
        tok
        for line in _SPEC_FAILURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("# ---- ")
        for tok in line.split() if tok.startswith("#4")
    })
    terminalreporter.write_sep("=", "KNOWN BROKEN, SPECIFIED, NOT FIXED", red=True)
    terminalreporter.write_line(
        f"  {len(known)} tests describe behaviour the code does not have yet."
    )
    terminalreporter.write_line(f"  Open: {', '.join(issues)}")
    terminalreporter.write_line(
        f"  Listed in tests/{_SPEC_FAILURES_PATH.name} — this is debt, not a pass."
    )
