"""Open a project by the name the sidebar shows (#5567).

WHY: an operator on the Air could only open a project by its .fichero package path; the name a
person sees in the sidebar was refused. `GET /api/registry/resolve?name=` finds the one known
project of that name (its registered name, else its package name without `.fichero`), so the CLI's
`--library` and the MCP's `fichero_use_library` take a name as well as a path.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.library.registry as registry
from fichero_server.api.main import app
from fichero_server.api.routes.library.registry import get_global_database
from fichero_server.db import Database
from fichero_server.models import KnownLibrary


@pytest.fixture
def known(tmp_path, monkeypatch):
    global_db = Database(path=tmp_path / "global.fichero" / "fichero.duckdb")
    app.dependency_overrides[get_global_database] = lambda: global_db
    monkeypatch.setattr(registry, "get_global_database", lambda: global_db)
    global_db.save(KnownLibrary(path="/Users/x/Istmina Full.fichero", name="Istmina Full"))
    global_db.save(KnownLibrary(path="/Users/x/Marshall Diaries.fichero"))  # no name: the package's
    try:
        yield global_db
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        global_db.conn.close()


def _resolve(client, name: str):
    return client.get("/api/registry/resolve", params={"name": name})


def test_a_project_is_found_by_its_shown_name_ignoring_case(client, known):
    response = _resolve(client, "istmina full")
    assert response.status_code == 200, response.text
    assert response.json()["path"] == "/Users/x/Istmina Full.fichero"


def test_a_project_with_no_registered_name_is_found_by_its_package_name(client, known):
    response = _resolve(client, "Marshall Diaries")
    assert response.status_code == 200, response.text
    assert response.json()["path"] == "/Users/x/Marshall Diaries.fichero"


def test_a_path_is_still_accepted(client, known):
    assert _resolve(client, "/Users/x/Istmina Full.fichero").json()["name"] == "Istmina Full"


def test_an_unknown_name_is_a_404_naming_the_known_projects(client, known):
    response = _resolve(client, "Istmina")
    assert response.status_code == 404
    assert "Istmina Full" in response.text and "Marshall Diaries" in response.text


def test_two_projects_of_one_name_is_a_409_naming_their_paths(client, known):
    known.save(KnownLibrary(path="/Volumes/Backup/Istmina Full.fichero", name="Istmina Full"))
    response = _resolve(client, "Istmina Full")
    assert response.status_code == 409
    assert "/Volumes/Backup/Istmina Full.fichero" in response.text
