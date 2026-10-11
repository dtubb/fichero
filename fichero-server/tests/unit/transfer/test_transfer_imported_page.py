"""A page imported the usual way stores its original as `files/...`, relative to its package (#5657, found
in the hands-on pass of #5659).

WHY: the transfer read every stored path as absolute, so a relative one resolved against the engine's working
directory, never inside the package. Every imported page then travelled as a "linked" original: no bytes were
copied, and the copy's path `files/...` named a file the target did not have. On a real project, every copy
or move would have arrived without its pictures, and a move would have sent the only reference to the Trash.
"""

from __future__ import annotations

from pathlib import Path

from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document, FileType

from tests.unit.transfer._two_projects import open_source, png


def test_an_imported_pages_original_travels_with_it_and_stays_package_relative(client, db, tmp_path):
    source_package = open_source(tmp_path)
    source = db_manager.get_database(source_package)
    png(source_package / "files" / "fi" / "abc_page.png", "red")
    page = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path="files/fi/abc_page.png")
    source.save(page)

    r = client.post("/api/documents/transfer", json={"items": [page.id], "source": str(source_package)})

    assert r.status_code == 200, r.text
    result = r.json()
    assert result["files"] == 1 and result["linked_files"] == []
    copy = db.get(Document, result["copies"][0])
    assert not Path(copy.path).is_absolute() and copy.path.startswith("files/")
    target_package = Path(db.path).parent
    assert (target_package / copy.path).read_bytes() == (source_package / page.path).read_bytes()
