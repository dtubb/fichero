"""
Shared pytest fixtures for all tests.

Provides fixtures for package documents testing with proper isolation.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from fichero.api.main import app
from fichero.db import db_manager


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
    db = db_manager.get_database(package_path)

    yield package_path

    # Cleanup
    db_manager.close_all()


@pytest.fixture
def client(test_package):
    """
    Create test client with proper X-Fichero-Library-Path header.

    This client automatically includes the library path header in all requests,
    so tests can make requests without needing to manually add headers.
    """
    # Create client with default headers
    client = TestClient(
        app,
        headers={"X-Fichero-Library-Path": str(test_package)}
    )

    return client


@pytest.fixture
def db(test_package):
    """
    Get the Database instance for the test package.

    Use this fixture when tests need direct database access
    (e.g., to set up test data before making API requests).
    """
    return db_manager.get_database(test_package)
