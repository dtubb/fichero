"""Shared fixture for the catalogue workbook tests."""
import pytest

from fichero_server.db import Database


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.duckdb")
    yield d
    d.close()
