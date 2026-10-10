"""Every project has a Sources folder, and an import that names no folder lands in it (#5413).

Spec: `sidebar.project.has-a-sources-folder` (docs/contributor_manual/specs/ui/sidebar-crud.md).

WHY: ruled 2026-10-04 while testing the dev DMG -- loose imports piled up at the top of a
project with nowhere obvious to go. The engine makes and chooses the folder so the app, CLI and
MCP agree on it; the app only shows it. Each test below pins one half of that rule through the
real routes and the real library open, because a rule split across the open path and five
import routes is exactly the kind that drifts when one route is added or rewritten.

REAL DATA: an existing project only GAINS a folder; nothing already in it moves. Two of these
tests pin that, since the projects it opens hold years of a person's work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.db import db_manager
from fichero_server.importers.sources_folder import SOURCES_FOLDER_NAME, find_sources_folder
from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import LibrarySetting


def _root_folders_named_sources(db) -> list[Document]:
    return [
        d
        for d in db.query(Document, parent_id=None, name=SOURCES_FOLDER_NAME)
        if d.doc_type == DocType.folder and d.deleted_at is None
    ]


def _make_it_an_older_project(db) -> None:
    """Undo what the open did, so the package reads like one made before #5413."""
    for folder in _root_folders_named_sources(db):
        db.delete(folder)
    marker = db.get(LibrarySetting, "sources_folder.created")
    if marker is not None:
        db.delete(marker)


def _reopen(package: Path):
    db_manager.close_database(package)
    return db_manager.get_database(package)


def test_a_new_project_is_created_with_its_sources_folder(tmp_path, monkeypatch):
    """WHY: a new project must have Sources before anything is imported, or the sidebar shows an
    empty project with no obvious place for material -- through the real `POST /api/library`."""
    from fastapi.testclient import TestClient

    from fichero_server.api.auth import initialize_token
    from fichero_server.api.main import app
    from fichero_server.api.routes.library import core as library_core

    monkeypatch.setattr(library_core, "_register_known_library", lambda *_a, **_k: None)
    target = tmp_path / "New Project.fichero"
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {initialize_token()}"

    response = client.post("/api/library", json={"path": str(target)})

    assert response.status_code == 200, response.text
    assert response.json()["created"] is True
    try:
        db = db_manager.get_database(target)
        assert len(_root_folders_named_sources(db)) == 1
    finally:
        db_manager.close_database(target)


def test_the_global_library_has_its_sources_folder_too(tmp_path):
    """WHY: on a first launch the app shows the global library (Local); with no Sources folder it
    opened on Workflows with nowhere for material to go (maintainer, 2026-10-10)."""
    package = tmp_path / "global.fichero"
    package.mkdir()
    try:
        db = db_manager.get_database(package)
        assert len(_root_folders_named_sources(db)) == 1
    finally:
        db_manager.close_database(package)


def test_an_import_naming_no_folder_lands_in_sources(client, db, tmp_path):
    """WHY: the whole point of the folder -- a drop onto the project (no folder named) used to land
    at the top level. The document's parent must be the Sources folder, not None."""
    source = tmp_path / "letter.txt"
    source.write_text("Querido hermano")

    response = client.post("/api/ingest/file", json={"path": str(source)})

    assert response.status_code == 200, response.text
    sources = find_sources_folder(db)
    assert sources is not None
    assert response.json()["parent_id"] == sources.id
    assert db.get(Document, response.json()["id"]).parent_id == sources.id


def test_an_uploaded_file_naming_no_folder_lands_in_sources(client, db):
    """WHY: the app's COPY import is a multipart upload (`POST /api/documents/import`), a different
    route from `/api/ingest/file`; one rule must cover both or a copy-drop lands at the top."""
    response = client.post(
        "/api/documents/import",
        files={"file": ("note.txt", b"a page of notes", "text/plain")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["parent_id"] == find_sources_folder(db).id


def test_a_folder_import_naming_no_folder_lands_in_sources(client, db, tmp_path):
    """WHY: a dropped folder becomes a folder node; with no target it must sit inside Sources,
    with its files under it -- not at the project's top level beside Sources."""
    box = tmp_path / "Box 3"
    box.mkdir()
    (box / "a.txt").write_text("one")

    response = client.post("/api/ingest/folder", json={"path": str(box)})

    assert response.status_code == 200, response.text
    sources = find_sources_folder(db)
    [box_doc] = [d for d in db.query(Document, name="Box 3") if d.doc_type == DocType.folder]
    assert box_doc.parent_id == sources.id
    [file_doc] = db.query(Document, name="a.txt")
    assert file_doc.parent_id == box_doc.id


def test_an_import_naming_a_folder_lands_there_not_in_sources(client, db, tmp_path):
    """WHY: Sources is only the default. A drop onto a named folder must keep going there, or the
    rule would silently redirect every targeted import."""
    target = Document(name="Correspondence", doc_type=DocType.folder)
    db.save(target)
    source = tmp_path / "reply.txt"
    source.write_text("Respuesta")

    response = client.post(
        "/api/ingest/file", json={"path": str(source), "parent_id": target.id}
    )

    assert response.status_code == 200, response.text
    assert response.json()["parent_id"] == target.id


def test_an_existing_project_gains_sources_on_open_and_nothing_moves(test_package):
    """WHY: projects made before #5413 must gain the folder the next time they open -- and the
    material already in them must stay exactly where the person put it (real data, never moved)."""
    db = db_manager.get_database(test_package)
    _make_it_an_older_project(db)
    loose = Document(name="loose.jpg", doc_type=DocType.file)
    folder = Document(name="Box 1", doc_type=DocType.folder)
    db.save(loose)
    db.save(folder)
    assert _root_folders_named_sources(db) == []

    db = _reopen(test_package)

    assert len(_root_folders_named_sources(db)) == 1
    assert db.get(Document, loose.id).parent_id is None
    assert db.get(Document, folder.id).parent_id is None


def test_a_root_folder_already_named_sources_is_the_sources_folder(test_package, client, tmp_path):
    """WHY: a person who already made a "Sources" folder must not get a second one beside it on
    open; theirs IS the Sources folder, and imports land in it with what is already there."""
    db = db_manager.get_database(test_package)
    _make_it_an_older_project(db)
    theirs = Document(name="Sources", doc_type=DocType.folder)
    db.save(theirs)
    inside = Document(name="old scan.jpg", doc_type=DocType.file, parent_id=theirs.id)
    db.save(inside)

    db = _reopen(test_package)

    assert [d.id for d in _root_folders_named_sources(db)] == [theirs.id]
    assert db.get(Document, inside.id).parent_id == theirs.id
    source = tmp_path / "new.txt"
    source.write_text("nuevo")
    response = client.post("/api/ingest/file", json={"path": str(source)})
    assert response.json()["parent_id"] == theirs.id


def test_a_deleted_sources_folder_is_not_remade_on_open_but_is_by_the_next_import(
    test_package, client, tmp_path
):
    """WHY: the Inbox this replaces came back on every open after a person deleted it (ruling
    2026-08-31). The open makes Sources once; only an import that needs it makes it again."""
    db = db_manager.get_database(test_package)
    for folder in _root_folders_named_sources(db):
        db.delete(folder)

    db = _reopen(test_package)
    assert _root_folders_named_sources(db) == []

    source = tmp_path / "after.txt"
    source.write_text("después")
    response = client.post("/api/ingest/file", json={"path": str(source)})
    assert response.status_code == 200, response.text
    [remade] = _root_folders_named_sources(db)
    assert response.json()["parent_id"] == remade.id


@pytest.fixture(autouse=True)
def _close_libraries(monkeypatch):
    # The conftest skips the open's half of the rule for every other test; these test it.
    monkeypatch.delenv("FICHERO_SKIP_SOURCES_FOLDER", raising=False)
    yield
    db_manager.close_all()
