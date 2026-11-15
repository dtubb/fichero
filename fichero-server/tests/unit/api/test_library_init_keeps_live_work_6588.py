"""`POST /api/library` on a project already open keeps its connection, and the work in flight in it (#6588, #6596).

Seen in the Dev Local build, 2026-11-14 night: the app relaunched, sent `POST /api/library` for its open project, and the
route's guard for a package deleted and recreated on disk (#1668) closed the project's connection; the Kraken run going
in it was stopped and ended FAILED ("Interrupted: the project was closed"). The guard now closes only a connection whose
file is gone or was replaced; the same file stays open.
"""
from __future__ import annotations

import shutil

from fichero_server.db.manager import db_manager


def _init(client, path):
    return client.post("/api/library", json={"path": str(path)})


def test_initialising_an_open_project_keeps_its_connection(client, tmp_path):
    package = tmp_path / "Open.fichero"
    assert _init(client, package).status_code == 200
    before = db_manager.open_database(db_manager._cache_key(package))
    assert before is not None
    assert _init(client, package).status_code == 200
    assert db_manager.open_database(db_manager._cache_key(package)) is before, "the same connection, not closed"


def test_a_package_deleted_and_made_again_gets_a_fresh_connection(client, tmp_path):
    package = tmp_path / "Again.fichero"
    assert _init(client, package).status_code == 200
    before = db_manager.open_database(db_manager._cache_key(package))
    shutil.rmtree(package)
    assert _init(client, package).status_code == 200
    after = db_manager.open_database(db_manager._cache_key(package))
    assert after is not None and after is not before, "#1668: the old handle pointed at a deleted file"
