"""Kept exports, the engine half (#5485).

Spec: `docs/contributor_manual/specs/source/models-chains-and-projects.md`, section 7b, screen 3
(**Kept exported**): the project keeps an up-to-date copy of its work in a folder outside it, one
row per export (folder, format, one file per page or per document); one-way, through the one export
path, as background jobs. Driven through the public surface: `POST /api/export/kept`,
`GET /api/export/kept`, `POST /api/export/kept/{id}/write`, written by jobs on the real scheduler.
Folders are pytest tmp folders only.
"""
from __future__ import annotations

import base64
import shutil
import time
import zipfile
from types import SimpleNamespace

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import read_page

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
#: A 1x1 PNG: the Word export puts a page's image beside its text, so the page needs a real one.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def page(db, client, tmp_path):
    """A page with a working pass (converted, one box moved through the real route), its image a
    real file, inside a two-page-capable parent file `book.pdf`."""
    from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
    from fichero_server.models import Artifact
    from tests.unit.api.seeded_converted_page import seed_page

    parent, doc, art = seed_page(db)
    image = tmp_path / "scans" / "book-p1.png"
    image.parent.mkdir()
    image.write_bytes(PNG)
    doc.path = str(image)
    db.save(doc)
    assert client.put(f"/api/artifacts/{art.id}/regions",
                      json={"op": "move", "indices": [3], "bbox": [0.5, 0.9, 0.1, 0.05]}).status_code == 200
    row = live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]
    return SimpleNamespace(id=doc.id, parent=parent, first_row=row)


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import kept_export, sync_folder

    monkeypatch.setattr(kept_export, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _keep(client, folder, fmt, per):
    r = client.post("/api/export/kept", json={"folder": str(folder), "format": fmt, "per": per})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _status(client, export_id):
    r = client.get("/api/export/kept")
    assert r.status_code == 200, r.text
    return next(e for e in r.json()["exports"] if e["id"] == export_id)


def _wait_for(predicate, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _written(client, export_id, files):
    return _wait_for(lambda: (s := _status(client, export_id))["pending"] == 0 and s["files"] == files)


def test_writes_alto_one_file_per_page_into_the_folder(client, page, tmp_path):
    """ALTO per page: one file per page, named by the page's file, written by the exporter (it
    reads back as ALTO with every line). WHY: a kept export that wrote its own XML would be a second
    export path, and its files would drift from what Export gives."""
    folder = tmp_path / "for-escriptorium"
    folder.mkdir()
    export_id = _keep(client, folder, "alto", "page")
    assert _written(client, export_id, ["book-p1.alto.xml"])
    back = read_page("alto", (folder / "book-p1.alto.xml").read_bytes())
    texts = sorted(s.readings[0][1] for s in back.segments if s.kind == "line" and s.readings)
    assert "In the year of our Lord" in texts and len(texts) == 4
    assert sorted(p.name for p in folder.iterdir()) == ["book-p1.alto.xml"]


def test_writes_word_one_file_per_document_named_after_it(client, page, tmp_path):
    """Word per document: the page's document (`book.pdf`) is one `.docx`, headed by its name, its
    page's text inside. WHY: Word is the reading copy a person hands on; one file per document is
    what the spec's example asks (Word per document for reading)."""
    folder = tmp_path / "reading"
    folder.mkdir()
    export_id = _keep(client, folder, "word", "document")
    assert _written(client, export_id, ["book.docx"])
    with zipfile.ZipFile(folder / "book.docx") as docx:
        body = docx.read("word/document.xml").decode("utf-8")
    assert "book.pdf" in body and "In the year of our Lord" in body and "sailed from Cadiz" in body


def test_writes_markdown_one_file_per_page_in_reading_order(client, page, tmp_path):
    """Markdown per page: headed by the page's name, its lines in reading order (the derived text, the
    same the Reader shows). WHY: Markdown had no writer; a page's text in some other order is a
    sentence nobody wrote."""
    folder = tmp_path / "notes"
    folder.mkdir()
    export_id = _keep(client, folder, "markdown", "page")
    assert _written(client, export_id, ["book-p1.md"])
    text = (folder / "book-p1.md").read_text(encoding="utf-8")
    assert text.startswith("# book p1\n")
    order = [text.index(line) for line in ("In the year of our Lord", "one thousand eight hundred",
                                           "and fifty two, the ship")]
    assert order == sorted(order)


def test_a_second_write_overwrites_only_its_own_files_and_leaves_a_stranger_alone(client, page, tmp_path):
    """One-way: a file the export wrote is overwritten at the next write, a hand edit to it included;
    a file it did not write -- beside its files, or where one of its files would go -- is never
    touched, and the one in its way is listed. WHY: the folder is the person's; an export that
    clobbered or deleted their files would lose work it never had."""
    folder = tmp_path / "out"
    folder.mkdir()
    stranger = folder / "my notes.txt"
    stranger.write_text("mine", encoding="utf-8")
    in_the_way = folder / "book-p1.alto.xml"
    in_the_way.write_text("<not ours/>", encoding="utf-8")

    markdown = _keep(client, folder, "markdown", "page")
    assert _written(client, markdown, ["book-p1.md"])
    ours = folder / "book-p1.md"
    ours.write_text("edited by hand", encoding="utf-8")
    r = client.post(f"/api/export/kept/{markdown}/write")
    assert r.status_code == 200, r.text
    assert r.json()["job_id"]
    assert _wait_for(lambda: ours.read_text(encoding="utf-8").startswith("# book p1"))

    alto = _keep(client, folder, "alto", "page")
    assert _wait_for(lambda: _status(client, alto)["pending"] == 0 and _status(client, alto)["in_the_way"])
    assert _status(client, alto)["in_the_way"] == ["book-p1.alto.xml"] and _status(client, alto)["files"] == []
    assert in_the_way.read_text(encoding="utf-8") == "<not ours/>"
    assert stranger.read_text(encoding="utf-8") == "mine"


def test_a_correction_rewrites_the_kept_file(client, db, page, tmp_path):
    """The work changing rewrites the file after the quiet period, with no "write now". WHY: an
    export that is only current when someone remembers to write it is not kept."""
    folder = tmp_path / "plain"
    folder.mkdir()
    export_id = _keep(client, folder, "plain-text", "page")
    assert _written(client, export_id, ["book-p1.txt"])
    rid = registry.invoke(db, "representation.create", {
        "document_id": page.id, "segment_id": page.first_row.id, "kind": "transcription",
        "content": "In the year of Our Lord and Saviour"}, CTX).result["id"]
    registry.invoke(db, "reading.choose", {"segment_id": page.first_row.id, "kind": "transcription",
                                           "representation_id": rid}, CTX)
    assert _wait_for(lambda: "and Saviour" in (folder / "book-p1.txt").read_text(encoding="utf-8"))


def test_refuses_a_system_folder_in_one_sentence(client, page):
    """A system folder is refused, as the owner's folder pick refuses it. WHY: an export writes files;
    `/usr` is not a place for a person's files."""
    r = client.post("/api/export/kept", json={"folder": "/usr", "format": "markdown", "per": "page"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, str) and "system folder" in detail and detail.count(". ") == 0
    assert client.get("/api/export/kept").json()["exports"] == []


def test_refuses_a_folder_inside_the_project(client, page, test_package):
    """A folder inside the project's package is refused. WHY: the export is a copy for outside; inside
    the package it would be the project writing into itself."""
    inside = test_package / "exports"
    inside.mkdir()
    r = client.post("/api/export/kept", json={"folder": str(inside), "format": "word", "per": "document"})
    assert r.status_code == 422
    assert r.json()["detail"] == "That folder is inside the project; choose one outside it."


def test_refuses_a_page_format_one_file_per_document(client, page, tmp_path):
    """ALTO describes one image, so per document is refused in words, not written wrongly."""
    r = client.post("/api/export/kept", json={"folder": str(tmp_path), "format": "alto", "per": "document"})
    assert r.status_code == 422 and "one file per page" in r.json()["detail"]


def test_a_kept_export_survives_a_restart(client, db, page, tmp_path, test_package):
    """Kept in the library database: the library file, opened again by a new engine (here a copy of
    it, opened cold), still holds the export with the files it wrote. WHY: "kept" means kept; an
    export held only in the running engine would be gone at the next launch."""
    from fichero_server import kept_export
    from fichero_server.db import Database

    folder = tmp_path / "kept"
    folder.mkdir()
    export_id = _keep(client, folder, "markdown", "document")
    assert _written(client, export_id, ["book.md"])
    db.execute("CHECKPOINT")
    copy = tmp_path / "after-restart.fichero"
    copy.mkdir()
    shutil.copy2(test_package / "fichero.duckdb", copy / "fichero.duckdb")
    reopened = Database(copy / "fichero.duckdb")
    try:
        [kept] = kept_export.status(reopened)
    finally:
        reopened.close()
    assert (kept["id"], kept["folder"], kept["format"], kept["per"], kept["files"]) == (
        export_id, str(folder.resolve()), "markdown", "document", ["book.md"])


def test_removing_a_kept_export_leaves_its_files(client, page, tmp_path):
    """Stopping keeping an export deletes nothing in the folder."""
    folder = tmp_path / "gone"
    folder.mkdir()
    export_id = _keep(client, folder, "markdown", "page")
    assert _written(client, export_id, ["book-p1.md"])
    assert client.delete(f"/api/export/kept/{export_id}").status_code == 200
    assert client.get("/api/export/kept").json()["exports"] == []
    assert (folder / "book-p1.md").exists()
    assert client.post(f"/api/export/kept/{export_id}/write").status_code == 404
