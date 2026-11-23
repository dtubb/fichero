"""`import.folder-shows-at-once` (#7066): a folder import and a IIIF add make their destination folder, and answer its
id, before any file is copied or any manifest is read."""
from __future__ import annotations

import pytest

from fichero_server.importers import iiif_source
from fichero_server.media.iiif_fetch import PoliteFetcher
from fichero_server.models import DocType, Document
from tests.unit.importers.test_iiif_by_reference import HOST, FakeIIIFServer, _manifest3


def test_a_folder_import_answers_the_folder_id_before_any_file_is_copied(client, db, tmp_path, monkeypatch):
    from fichero_server.importers import ingest

    dropped = tmp_path / "Letters"
    dropped.mkdir()
    (dropped / "a.txt").write_text("hello")
    seen: dict = {}

    def refuse_to_copy(folder, **kwargs):
        # The import is about to copy its first file: the folder row must already be there.
        seen["rows"] = [d for d in db.query(Document, name="Letters") if d.doc_type == DocType.folder]
        raise RuntimeError("stopped before any file")

    monkeypatch.setattr(ingest, "ingest_folder", refuse_to_copy)

    started = client.post("/api/ingest/folder", json={"path": str(dropped), "mode": "copy"})

    assert started.status_code == 200, started.text
    folder_id = started.json()["folder_id"]
    assert folder_id and [d.id for d in seen["rows"]] == [folder_id]
    status = client.get(f"/api/ingest/status/{started.json()['task_id']}").json()
    assert status["status"] == "failed" and status["folder_id"] == folder_id
    assert db.get(Document, folder_id) is not None, "a failed import leaves its folder row"


def test_a_folder_import_fills_the_folder_it_answered(client, db, tmp_path):
    from PIL import Image

    dropped = tmp_path / "Scans"
    dropped.mkdir()
    Image.new("RGB", (40, 60), "white").save(dropped / "p1.jpg")

    started = client.post("/api/ingest/folder", json={"path": str(dropped), "mode": "copy", "extract_text": False,
                                                       "auto_embed": False})

    folder_id = started.json()["folder_id"]
    assert len([d for d in db.query(Document, name="Scans") if d.doc_type == DocType.folder]) == 1
    assert [d.name for d in db.query(Document, parent_id=folder_id)] == ["p1.jpg"]


def test_a_iiif_add_answers_its_folder_before_the_manifest_is_read(db):
    url = f"{HOST}/vol1/manifest"
    job_id, folder_id, made = iiif_source.start(db, url, folder_id=None, started_by="test")

    folder = db.get(Document, folder_id)
    assert made and job_id and folder.doc_type == DocType.folder and folder.name == "iiif.archive.example"
    assert db.query(Document, parent_id=folder_id) == [], "no canvas yet"

    manifest = _manifest3("vol1", 3)
    server = FakeIIIFServer({manifest["id"]: manifest})
    done = iiif_source.import_source(db, url, folder_id=folder_id,
                                     fetcher=PoliteFetcher(get=server.get, sleep=lambda s: None))

    assert done["folder_id"] == folder_id and len(db.query(Document, parent_id=folder_id)) == 3
    assert db.get(Document, folder_id).name == "vol1", "the manifest's label replaces the host"
    assert iiif_source.PROVISIONAL_NAME not in db.get(Document, folder_id).metadata


@pytest.mark.parametrize("url", [f"{HOST}/a/manifest"])
def test_a_second_iiif_add_of_the_same_source_answers_the_same_folder(db, url):
    _, first, first_made = iiif_source.start(db, url, folder_id=None, started_by="test")
    _, second, second_made = iiif_source.start(db, url, folder_id=None, started_by="test")
    assert first == second and first_made and not second_made, "only the call that made the folder says so"
