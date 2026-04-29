"""
Shared pytest fixtures for all tests.

Provides fixtures for package documents testing with proper isolation.
"""

import pytest
import inspect
import asyncio
import os
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

# Keep existing route-heavy tests running against the broader dev API surface.
os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
# Tests assume a clean library by default — disable automatic preset seeding
# so assertions like "GET /workflows returns []" keep working.
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.api.main import app
from fichero.db import db_manager
from fichero.app_db import AppDatabase


def pytest_collection_modifyitems(items):
    """
    Auto-mark coroutine tests so they run with the installed anyio plugin.
    """
    for item in items:
        test_obj = getattr(item, "obj", None)
        if test_obj is not None and inspect.iscoroutinefunction(test_obj):
            item.add_marker(pytest.mark.anyio)


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
    """
    app_db_path = tmp_path / "test_app.duckdb"
    db = AppDatabase(path=app_db_path)

    yield db

    # Cleanup
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
    from fichero.api.main import get_library_database
    from fichero.api.routes.providers import get_app_database

    # Override dependencies to use test dbs
    app.dependency_overrides[get_app_database] = lambda: app_db
    app.dependency_overrides[get_library_database] = lambda: db_manager.get_database(test_package)

    # Create client with default headers
    client = TestClient(
        app,
        headers={"X-Fichero-Library-Path": str(test_package)}
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
