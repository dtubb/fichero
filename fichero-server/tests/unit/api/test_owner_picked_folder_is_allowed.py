"""A folder the owner picks in the app's own panel is readable by its own engine (#5484).

WHY: the maintainer picked "Spanish - early modern notarial register (Transkribus)" in setup ›
Add a Folder… and was told Fichero may not read it: the app hands the pick to
POST /api/sandbox/security-scoped-access, and an unsandboxed (Dev Local, terminal) engine refused
it with a 400 by design (audit A1: no widening from a bookmark). Picking a folder in Fichero's own
panel IS the permission, so when the OWNER (loopback + bootstrap token) sends it, the engine
allows that exact folder and everything under it, and remembers it across a restart. Everyone
else -- a paired device, a remote session -- keeps the A1 refusal; a path with `..`, a symlink to
a system folder and a system folder itself are refused whoever asks.

Through the real routes: the grant route, then POST /api/ingest/file with the real path check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

import fichero_server.api.routes.library.registry as registry
import fichero_server.security.path_security as path_security
from fichero_server.api.main import app
from fichero_server.api.routes.auth import sandbox_access
from fichero_server.api.routes.library.registry import get_global_database
from fichero_server.db import Database
from fichero_server.models import Document

GRANT = "/api/sandbox/security-scoped-access"
BOOKMARK = "Ym9va21hcms="  # what the app sends; an unsandboxed engine never needs it for the owner


@pytest.fixture
def picked(tmp_path, monkeypatch, client, test_package):
    """A material folder in a folder of HOME that is no allowed root, like the maintainer's."""
    fake_home = tmp_path / "home"
    folder = fake_home / "Spanish - early modern notarial register (Transkribus)"
    (folder / "pages").mkdir(parents=True)
    (folder / "pages" / "page-001.txt").write_text("En la ciudad de Mérida")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.delenv("APP_SANDBOX_CONTAINER_ID", raising=False)  # Dev Local: unsandboxed

    # tmp_path sits under the OS temp roots, which are allowed for CI. Drop the roots that contain
    # the fake home (keeping the test library) so the folder is outside every root exactly as the
    # maintainer's was -- otherwise the refusal could never be reproduced here.
    real_roots = path_security.ingest_allowed_roots
    monkeypatch.setattr(
        path_security,
        "ingest_allowed_roots",
        lambda: [test_package.resolve()]
        + [root for root in real_roots() if not fake_home.resolve().is_relative_to(root)],
    )
    monkeypatch.setattr(path_security, "_OWNER_GRANTED_FOLDERS", set())

    global_db = Database(path=tmp_path / "global.fichero" / "fichero.duckdb")
    app.dependency_overrides[get_global_database] = lambda: global_db
    monkeypatch.setattr(registry, "get_global_database", lambda: global_db)
    monkeypatch.setattr(registry, "_OWNER_OPENED_LOADED", False)
    try:
        yield folder
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        global_db.conn.close()


def _import(client: TestClient, path: Path):
    return client.post("/api/ingest/file", json={"path": str(path)})


def _grant(caller: TestClient, path: Path | str):
    return caller.post(GRANT, json={"path": str(path), "bookmark": BOOKMARK})


def _restart_engine(monkeypatch):
    """What a new engine process starts with: no in-memory grants, nothing loaded yet."""
    monkeypatch.setattr(path_security, "_OWNER_GRANTED_FOLDERS", set())
    monkeypatch.setattr(registry, "_OWNER_OPENED_LOADED", False)


def test_a_folder_the_owner_picked_imports_its_files(picked, client, db):
    """WHY: the reported bug -- the pick must just work, including files deeper in the folder."""
    page = picked / "pages" / "page-001.txt"
    refused = _import(client, page)
    assert refused.status_code == 403, "precondition: the folder is outside every root"
    assert refused.json()["code"] == "library_outside_allowed_locations"

    granted = _grant(TestClient(app), picked)  # the app on this Mac: loopback, the owner
    assert granted.status_code == 200, granted.text
    assert granted.json()["granted"] is True

    imported = _import(client, page)
    assert imported.status_code == 200, imported.text
    stored = db.get(Document, imported.json()["id"])
    assert stored is not None and stored.name == "page-001.txt"


def test_the_owner_grant_survives_an_engine_restart(picked, client, monkeypatch):
    """WHY: the owner picks once; an engine restart (the app does not pick again) must not
    bring the refusal back."""
    assert _grant(TestClient(app), picked).status_code == 200
    rows = registry.get_global_database().execute_fetchall("SELECT path FROM owner_granted_folders")
    assert rows == [(str(picked.resolve()),)]

    _restart_engine(monkeypatch)

    assert _import(client, picked / "pages" / "page-001.txt").status_code == 200


def test_a_paired_device_grant_is_refused_and_widens_nothing(picked, client, monkeypatch):
    """WHY: audit A1 -- a caller off this Mac (a paired device, a remote session) must never add
    a folder to what this engine reads, now or after a restart."""
    remote = TestClient(app, client=("10.0.0.7", 50000))
    assert _grant(remote, picked).status_code in (400, 403)

    # A paired device that IS authenticated (its own token, not the bootstrap one) reaches the
    # route itself: still the A1 refusal, never the owner's branch.
    paired = Request({"type": "http", "client": ("10.0.0.7", 50000), "headers": [], "state": {}})
    payload = sandbox_access.SecurityScopedAccessRequest(path=str(picked), bookmark=BOOKMARK)
    with pytest.raises(HTTPException) as refused:
        sandbox_access.create_security_scoped_access(payload, paired)
    assert refused.value.status_code == 400

    assert path_security._OWNER_GRANTED_FOLDERS == set()
    assert registry.get_global_database().execute_fetchall("SELECT path FROM owner_granted_folders") == []
    assert _import(client, picked / "pages" / "page-001.txt").status_code == 403

    _restart_engine(monkeypatch)
    assert _import(client, picked / "pages" / "page-001.txt").status_code == 403


def test_a_path_with_dotdot_is_refused_and_cannot_escape_a_granted_folder(picked, client):
    """WHY: `..` must neither be granted (it could name HOME or `/`) nor walk a file out of a
    folder that was granted."""
    owner = TestClient(app)
    escaping = _grant(owner, f"{picked}/../../..")
    assert escaping.status_code == 400, escaping.text

    assert _grant(owner, picked).status_code == 200
    secret = picked.parent / "Private" / "diary.txt"
    secret.parent.mkdir()
    secret.write_text("not material")
    assert _import(client, Path(f"{picked}/../Private/diary.txt")).status_code == 403


@pytest.mark.parametrize("system", [
    "/", "/System", "/etc", "/Volumes", "HOME", "HOME/Library/Keychains", "HOME/.ssh",
    "HOME/Library/Mobile Documents",
])
def test_a_system_folder_is_refused_even_for_the_owner(picked, client, system):
    """WHY: picking a folder allows everything under it; `/`, the OS's folders, HOME itself,
    ~/Library and HOME's hidden folders hold credentials and settings, never material."""
    home = Path.home()
    path = Path(system.replace("HOME", str(home)))
    if system.startswith("HOME/"):
        path.mkdir(parents=True)

    refused = _grant(TestClient(app), path)

    assert refused.status_code == 400, refused.text
    assert "system folder" in refused.json()["detail"]
    assert registry.get_global_database().execute_fetchall("SELECT path FROM owner_granted_folders") == []


@pytest.mark.parametrize("synced", [
    "HOME/Library/Mobile Documents/com~apple~CloudDocs/Archive",
    "HOME/Library/CloudStorage/Dropbox/Archive",
])
def test_a_folder_in_icloud_drive_or_a_cloud_drive_is_allowed(picked, client, synced):
    """WHY: historians keep material in iCloud Drive or Dropbox, which live under ~/Library;
    refusing all of ~/Library refused their archives."""
    path = Path(synced.replace("HOME", str(Path.home())))
    path.mkdir(parents=True)

    assert _grant(TestClient(app), path).status_code == 200


def test_a_drive_under_volumes_is_allowed_but_volumes_itself_is_not():
    """WHY: archives often sit on an external drive; only /Volumes itself (every drive) is refused."""
    from fichero_server.security.path_security import OwnerFolderGrantRefused, owner_folder_grant_key

    with pytest.raises(OwnerFolderGrantRefused):
        owner_folder_grant_key("/Volumes")
    drives = [d for d in Path("/Volumes").iterdir() if d.is_dir()] if Path("/Volumes").exists() else []
    if not drives:
        pytest.skip("no mounted volume to pick on this machine")
    assert owner_folder_grant_key(drives[0]) == str(drives[0].resolve())


def test_a_symlink_to_a_system_folder_is_that_system_folder(picked, client):
    """WHY: symlinks resolve first, so a folder named like material but linked to /etc is /etc."""
    link = picked.parent / "Looks Like Material"
    link.symlink_to("/etc", target_is_directory=True)

    assert _grant(TestClient(app), link).status_code == 400
    assert _import(client, link / "hosts").status_code == 403


def test_the_refusal_says_how_to_allow_it_in_one_step(picked, client):
    """WHY: "Choose Grant Access… to allow it, then drop it again" sent the maintainer round a
    loop; the refusal names the one step that allows it: picking the folder in Fichero."""
    detail = _import(client, picked / "pages" / "page-001.txt").json()["detail"]

    assert "drop it again" not in detail
    assert "Add a Folder" in detail
