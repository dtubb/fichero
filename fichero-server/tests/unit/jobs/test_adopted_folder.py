"""Index: importing a folder adopts it as a synced folder kept in its own layout (#4952).

Spec: docs/contributor_manual/specs/source/synced-folder.md, "Adopting an existing folder" and the
ruling that Index updates the originals in place. Written from the spec's behaviours before the
code, and driven through the public surface: the folder comes in through the audited
`import.folder` action (the one import path the route, CLI and MCP share) with `mode: index`, is
followed with `GET /api/sync-folders`, and is written by jobs on the real scheduler. Edits go
through the audited action layer, as the app's do.

Not covered here because not built yet: adopting a TEI file that spans several images. Edits
made in the folder coming in are in `test_synced_folder_intake.py`.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from _scan_files import scan_rglob

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry

FIXTURES = Path(__file__).resolve().parents[1] / "formats" / "fixtures"
CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
LAYOUT = "page/M_Otterskirchen_012_0002.xml"


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


@pytest.fixture
def kept_folder(tmp_path) -> Path:
    """A folder someone keeps, as Transkribus lays it out: the image, its PAGE XML in `page/`
(eScriptorium's own sample page, naming this image; its page made tall enough to hold its
    lines, which the sample overruns)."""
    from PIL import Image

    folder = tmp_path / "kept"
    (folder / "page").mkdir(parents=True)
    Image.new("RGB", (864, 300), "white").save(folder / "M_Otterskirchen_012_0002.jpg")
    (folder / LAYOUT).write_bytes((FIXTURES / "escriptorium_export.page.xml").read_bytes()
                                 .replace(b"default.png", b"M_Otterskirchen_012_0002.jpg")
                                 .replace(b'imageHeight="206"', b'imageHeight="300"'))
    return folder


def _import(db, folder, mode):
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    return registry.invoke(db, "import.folder", {"path": str(folder), "mode": mode}, ctx).result


def _folders(client):
    r = client.get("/api/sync-folders")
    assert r.status_code == 200, r.text
    return r.json()["folders"]


def _wait_for(predicate, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _correct(db, document_id, text):
    """Correct the first line of the page's pass, through the audited actions the app uses."""
    from fichero_server.models.segments import Segment, SegmentPass

    pass_ids = {p.id for p in db.all(SegmentPass) if p.document_id == document_id}
    row = next(s for s in db.all(Segment) if s.pass_id in pass_ids and s.kind == "line")
    rid = registry.invoke(db, "representation.create", {
        "document_id": document_id, "segment_id": row.id, "kind": "transcription", "content": text},
        CTX).result["id"]
    registry.invoke(db, "reading.choose", {"segment_id": row.id, "kind": "transcription",
                                           "representation_id": rid}, CTX)


def _page_id(db, result):
    from fichero_server.models import Document

    return next(d.id for d in (db.get(Document, i) for i in result["document_ids"])
                if d and d.name.endswith(".jpg"))


def test_source_sync_four_ways_in__index_leaves_the_originals_in_place_and_adopts_the_folder(
        client, db, kept_folder):
    """Behaviour `source.sync.four-ways-in`: "setup and import offer Link, Copy, Move and Index with
    what each does to the originals." Index (the maintainer's ruling) works on the folder in place:
    importing moves and copies nothing, changes no file, and the folder becomes a synced folder."""
    before = {p: p.read_bytes() for p in scan_rglob(kept_folder, "*") if p.is_file()}
    _import(db, kept_folder, "index")
    assert {p: p.read_bytes() for p in scan_rglob(kept_folder, "*") if p.is_file()} == before
    [folder] = _folders(client)
    assert Path(folder["path"]) == kept_folder.resolve()
    assert folder["adopted"] is True and folder["files"] == [LAYOUT]


def test_source_sync_four_ways_in__link_adopts_no_folder(client, db, kept_folder):
    """Behaviour `source.sync.four-ways-in`: Link never changes the original, and is not Index: it
    ties no folder, so nothing will ever be written there."""
    _import(db, kept_folder, "link")
    assert _folders(client) == []


def test_source_sync_adopt_existing_folder__work_is_written_back_into_the_same_file(client, db, kept_folder):
    """Behaviour `source.sync.adopt-existing-folder`: "it keeps its own layout ... work in Fichero is
    written back into the same file in the same format." A correction lands in the very file the
    page came from, still PAGE XML, after the quiet period; no subfolder of Fichero's is made."""
    page_id = _page_id(db, _import(db, kept_folder, "index"))
    _correct(db, page_id, "Otterskirchen, im Jahr des Herrn")
    path = kept_folder / LAYOUT
    assert _wait_for(lambda: "im Jahr des Herrn" in path.read_text(encoding="utf-8"))
    assert "PcGts" in path.read_text(encoding="utf-8")
    assert sorted(p.name for p in kept_folder.iterdir()) == ["M_Otterskirchen_012_0002.jpg", "page"]
    assert sorted(p.name for p in (kept_folder / "page").iterdir()) == ["M_Otterskirchen_012_0002.xml"]


def test_source_sync_adopt_existing_folder__a_file_changed_since_it_was_read_is_not_overwritten(
        client, db, kept_folder):
    """Behaviour `source.sync.adopt-existing-folder`: "it records each file's checksum when it reads
    it, and writes back only if the file is unchanged since; a file edited meanwhile is a conflict."
    The person's edit stays as they left it and the file is listed as a conflict (both kept as
    passes: `test_synced_folder_intake.py`)."""
    page_id = _page_id(db, _import(db, kept_folder, "index"))
    path = kept_folder / LAYOUT
    edited = path.read_text(encoding="utf-8").replace("</PcGts>", "<!-- edited in Oxygen --></PcGts>")
    path.write_text(edited, encoding="utf-8")
    _correct(db, page_id, "Otterskirchen, im Jahr des Herrn")
    folder_id = _folders(client)[0]["id"]
    assert _wait_for(lambda: next(f for f in _folders(client) if f["id"] == folder_id)["conflicts"] == [LAYOUT])
    assert path.read_text(encoding="utf-8") == edited
