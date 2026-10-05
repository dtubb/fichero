"""A project the app has open is never refused by its own engine (#5464).

WHY: the Dev Local engine (unsandboxed, started from the terminal) refused three projects in
~/Fichero Test Library with `failed_check=roots`, so every Activity poll for them was a 403,
while a project under ~/Documents worked. That folder is in no fixed root, and an unsandboxed
engine cannot read the app's bookmarks. The app notes every project it opens through
`POST /api/registry/add`; when the OWNER (loopback) does that, the engine serves that exact
package. The roots check stays fail-closed for everything else: an unknown path, a project's
parent folder, and a project registered by a non-owner caller are all still refused.

These go through the real routes (registry add, then GET /api/activity/jobs with the library
header) with the real library-database dependency -- no override of the check under test.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import fichero_server.api.routes.library.registry as registry
import fichero_server.security.path_security as path_security
from fichero_server.api.main import app
from fichero_server.api.routes.library.registry import get_global_database
from fichero_server.db import Database
from fichero_server.db.manager import db_manager


@pytest.fixture
def home_project(tmp_path, monkeypatch, app_db):
    """An Acceptance project in a folder of HOME that is no allowed root, like the maintainer's."""
    fake_home = tmp_path / "home"
    project = fake_home / "Fichero Test Library" / "Acceptance 2026-09-27b.fichero"
    project.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # pytest's tmp_path sits under the OS temp roots (/var/folders, /tmp), which are allowed for
    # CI. Drop the roots that contain the fake home, so the project is outside every root exactly
    # as ~/Fichero Test Library is -- otherwise the refusal could never be reproduced here.
    real_roots = path_security.ingest_allowed_roots
    monkeypatch.setattr(
        path_security,
        "ingest_allowed_roots",
        lambda: [root for root in real_roots() if not fake_home.resolve().is_relative_to(root)],
    )
    monkeypatch.setattr(path_security, "_OPENED_PACKAGES", set())

    global_db = Database(path=tmp_path / "global.fichero" / "fichero.duckdb")
    app.dependency_overrides[get_global_database] = lambda: global_db
    # The restart loader reads the global DB by name (it runs outside any request dependency).
    monkeypatch.setattr(registry, "get_global_database", lambda: global_db)
    monkeypatch.setattr(registry, "_OWNER_OPENED_LOADED", False)
    try:
        yield project
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        db_manager.close_all()
        global_db.conn.close()


def _jobs(client: TestClient, library: Path):
    return client.get("/api/activity/jobs", headers={"X-Fichero-Library-Path": quote(str(library), safe="/")})


def test_a_project_the_owner_opened_is_served_by_activity(home_project, caplog):
    owner = TestClient(app)  # the app on this Mac: loopback

    refused = _jobs(owner, home_project)
    assert refused.status_code == 403, "precondition: the project is outside every root"
    assert refused.json()["code"] == "library_outside_allowed_locations"
    assert "failed_check=roots" in caplog.text

    added = owner.post("/api/registry/add", params={"path": str(home_project)})
    assert added.status_code == 200, added.text

    served = _jobs(owner, home_project)
    assert served.status_code == 200, served.text
    assert "jobs" in served.json()


def test_an_unknown_path_is_still_refused_with_failed_check_roots(home_project, caplog):
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})

    stranger = home_project.parent / "Not Opened.fichero"
    stranger.mkdir()
    response = _jobs(owner, stranger)

    assert response.status_code == 403
    assert response.json()["code"] == "library_outside_allowed_locations"
    assert f"path={stranger}" in caplog.text and "failed_check=roots" in caplog.text


def test_opening_a_project_does_not_allow_its_folder_or_a_sibling_by_dotdot(home_project):
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})

    sibling = home_project.parent / "Sibling.fichero"
    sibling.mkdir()
    assert _jobs(owner, sibling).status_code == 403
    assert _jobs(owner, Path(f"{home_project}/../Sibling.fichero")).status_code == 403


def test_a_non_owner_registering_a_project_does_not_widen_the_check(home_project):
    """A caller off this Mac (a paired device, a remote session) is not the owner; its registry
    add must not promote a path into what the engine opens (audit A1)."""
    remote = TestClient(app, client=("10.0.0.7", 50000))
    remote.post("/api/registry/add", params={"path": str(home_project)})

    assert _jobs(TestClient(app), home_project).status_code == 403


def test_forgetting_the_project_refuses_it_again(home_project):
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})
    assert _jobs(owner, home_project).status_code == 200

    removed = owner.delete(f"/api/registry/{quote(str(home_project), safe='')}")
    assert removed.status_code == 200, removed.text

    assert _jobs(owner, home_project).status_code == 403


# --- #5464 follow-up: the allowance survives an engine restart ---------------------------------
# WHY: after an engine restart the app did not always register its open project again, so the
# maintainer's "Acceptance 2026-09-27b" was refused (403 failed_check=roots) on every Activity
# poll -- 718 times in one log. A restart is simulated by emptying the in-memory allowance and the
# loaded flag, exactly what a new engine process starts with; the global DB is what persists.


def _restart_engine(monkeypatch):
    monkeypatch.setattr(path_security, "_OPENED_PACKAGES", set())
    monkeypatch.setattr(registry, "_OWNER_OPENED_LOADED", False)


def _owner_rows():
    return registry.get_global_database().execute_fetchall("SELECT path FROM owner_opened_packages")


def test_a_project_the_owner_opened_is_still_served_after_a_restart(home_project, monkeypatch):
    """WHY: the reported bug -- the owner opened it, the engine restarted, the app did not
    register it again, and the project must still be served."""
    owner = TestClient(app)
    assert owner.post("/api/registry/add", params={"path": str(home_project)}).status_code == 200
    assert len(_owner_rows()) == 1

    _restart_engine(monkeypatch)

    served = _jobs(owner, home_project)
    assert served.status_code == 200, served.text


def test_a_non_owner_registration_is_not_persisted_and_stays_refused_after_restart(
    home_project, monkeypatch
):
    """WHY: persistence must not become a way round audit A1 -- a paired device or remote session
    that registers a project writes a registry row but never an owner allowance."""
    remote = TestClient(app, client=("10.0.0.7", 50000))
    remote.post("/api/registry/add", params={"path": str(home_project)})
    assert _owner_rows() == []

    _restart_engine(monkeypatch)

    assert _jobs(TestClient(app), home_project).status_code == 403


def test_removing_the_project_refuses_it_after_a_restart(home_project, monkeypatch):
    """WHY: closing a project withdraws the allowance; a restart must not bring it back."""
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})
    removed = owner.delete(f"/api/registry/{quote(str(home_project), safe='')}")
    assert removed.status_code == 200, removed.text
    assert _owner_rows() == []

    _restart_engine(monkeypatch)

    assert _jobs(owner, home_project).status_code == 403


def test_a_registry_row_removed_by_anyone_is_not_reloaded(home_project, monkeypatch):
    """WHY: loading needs the owner row AND the registry row, so a project no longer in the
    registry is never served after a restart, whoever removed it."""
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})
    # A removal by a caller that is not the owner (a signed-in CLI, say) deletes only the registry
    # row; the owner row stays behind.
    from fichero_server.models import KnownLibrary

    global_db = registry.get_global_database()
    for row in global_db.query(KnownLibrary, path=str(home_project.resolve())):
        global_db.delete(row)
    assert len(_owner_rows()) == 1, "precondition: the owner row is still there"

    _restart_engine(monkeypatch)

    assert _jobs(owner, home_project).status_code == 403


def test_an_unflagged_legacy_registry_row_is_refused(home_project, monkeypatch):
    """WHY: rows written before this fix (or by any non-owner path) carry no owner allowance, so
    nothing widens silently on upgrade. The owner's next open registers it again."""
    from fichero_server.models import KnownLibrary

    registry.get_global_database().save(KnownLibrary(path=str(home_project.resolve()), name="legacy"))

    _restart_engine(monkeypatch)

    assert _jobs(TestClient(app), home_project).status_code == 403


def test_a_persisted_package_replaced_by_a_symlink_is_not_reloaded(home_project, monkeypatch):
    """WHY: exact package only -- if the stored path now resolves elsewhere (a symlink planted
    where the project was), the reload must not follow it."""
    owner = TestClient(app)
    owner.post("/api/registry/add", params={"path": str(home_project)})

    elsewhere = home_project.parent.parent / "Elsewhere" / "Other.fichero"
    elsewhere.mkdir(parents=True)
    db_manager.close_database(str(home_project))
    shutil.rmtree(home_project)
    home_project.symlink_to(elsewhere, target_is_directory=True)

    _restart_engine(monkeypatch)

    assert _jobs(owner, home_project).status_code == 403
