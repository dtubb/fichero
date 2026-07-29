"""
Shared pytest fixtures for all tests.

Provides fixtures for package documents testing with proper isolation.
"""

import asyncio
import faulthandler
import inspect
import os
import pytest
from unittest.mock import MagicMock

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


def _make_test_base_path() -> _pathlib.Path:
    """Create a per-process base path for test-only app storage.

    Concurrent verifier runs must never point at the same DuckDB path,
    or they can deadlock on the exclusive database lock.
    """

    return _pathlib.Path(
        _tempfile.mkdtemp(prefix=f"{_TEST_BASE_PREFIX}{os.getpid()}-")
    )


_sweep_abandoned_test_base_paths()
_test_base = _make_test_base_path()
os.environ.setdefault("FICHERO_BASE_PATH", str(_test_base))
# Normal-exit cleanup. Cannot fire on SIGKILL, which is why the startup sweep
# above exists as the durable half rather than the belt-and-braces one.
_atexit.register(_shutil.rmtree, _test_base, True)

from fichero.api.main import app  # noqa: E402
from fichero.db import db_manager  # noqa: E402
from fichero.db.app import AppDatabase  # noqa: E402

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

    timeout = _deadlock_dump_timeout_seconds()
    if timeout is None:
        _deadlock_dump_armed = False
        return
    if not faulthandler.is_enabled():
        faulthandler.enable(all_threads=True)
    faulthandler.dump_traceback_later(timeout, repeat=False)
    _deadlock_dump_armed = True


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Cancel the hang dump alarm once the suite exits normally."""
    global _deadlock_dump_armed

    if _deadlock_dump_armed:
        faulthandler.cancel_dump_traceback_later()
        _deadlock_dump_armed = False


def pytest_collection_modifyitems(items):
    """
    Auto-mark coroutine tests so they run with the installed anyio plugin.
    """
    for item in items:
        test_obj = getattr(item, "obj", None)
        if test_obj is not None and inspect.iscoroutinefunction(test_obj):
            item.add_marker(pytest.mark.anyio)


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
    # Mirror the binary lookup in fichero.llm._apple_intelligence_chat.
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "fichero-engine" / "src" / "fichero"
        / "resources" / "bin" / "fm-bridge",
        repo_root / "fichero-engine" / "bin" / "fm-bridge" / "fm-bridge",
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


def pytest_collection_modifyitems(items):  # noqa: F811 — extends prior hook
    """Auto-mark async + apply Apple-availability skips."""
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

    import fichero.db.app as _app_db_module
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
    from fichero.api.main import get_library_database, get_library_database_for_write
    from fichero.api.routes.entities import _digest_library_database
    from fichero.api.routes.providers import get_app_database

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
# fichero.api.main pollution guard (#4243)
# =============================================================================
# Several suites `importlib.reload(fichero.api.main)` with auth env flipped to
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
    """Reload fichero.api.main under the suite-default auth env."""
    import importlib
    import sys

    module = sys.modules.get("fichero.api.main")
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

    module = sys.modules.get("fichero.api.main")
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
