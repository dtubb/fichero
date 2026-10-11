"""`importer.a-folder-is-never-one-file`: a folder is never recorded as a single file.

Seen 2026-10-11 in a dev engine's log: a document whose file was the folder `CACIQUES_INDIOS,17,D.5` itself, and
"Image generation failed for CACIQUES_INDIOS,17,D.5 (.5): [Errno 21] Is a directory" every time its picture was
asked for. The files import and document create refuse a folder in words (add it as a folder instead), and a
document already recorded that way has its picture refused once, said once, never retried.
"""

from __future__ import annotations

import logging

from fichero_server.db import storage


def _folder(tmp_path):
    folder = tmp_path / "CACIQUES_INDIOS,17,D.5"
    folder.mkdir()
    (folder / "p1.jpg").write_bytes(b"not read")
    return folder


def test_the_files_import_refuses_a_folder_in_words(client, tmp_path):
    folder = _folder(tmp_path)
    for route, body in (("/api/ingest/file", {"path": str(folder)}), ("/api/ingest/files", {"paths": [str(folder)]})):
        r = client.post(route, json=body)
        assert r.status_code == 400, (route, r.text)
        said = r.json()["detail"]
        assert "is a folder" in said and "Add it as a folder" in said, said
        assert str(tmp_path) not in said, said


def test_document_create_refuses_a_file_document_whose_path_is_a_folder(client, test_package):
    from pathlib import Path

    folder = Path(test_package) / "media" / "a-folder"
    folder.mkdir(parents=True)
    r = client.post("/api/documents", json={"name": "a-folder", "doc_type": "file", "path": str(folder)})
    assert r.status_code == 400, r.text
    assert "is a folder" in r.json()["detail"], r.json()
    # A folder node is still made as a folder.
    assert client.post("/api/documents", json={"name": "Box 1", "doc_type": "folder"}).status_code in (200, 201)


def test_a_folder_recorded_as_a_file_has_its_picture_refused_once(tmp_path, caplog):
    folder = _folder(tmp_path)
    with caplog.at_level(logging.INFO, logger=storage.logger.name):
        for _ in range(3):
            assert storage._generate_image(folder, tmp_path / "out.jpg", (64, 64)) is None
    said = [r.getMessage() for r in caplog.records if folder.name in r.getMessage()]
    assert len(said) == 1 and "is a folder" in said[0], said
    assert "Image generation failed" not in " ".join(said)
