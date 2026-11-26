"""#7093: a project's own files (files/, storage/) are stored relative to the package, so a copied or moved project finds
them. On open, an absolute path that points inside ANY earlier location of this package and whose tail exists here is
rewritten to a relative one: once, audited, ids untouched; a linked original outside the package keeps its path."""
from __future__ import annotations

import shutil

from fichero_server.db import db_manager
from fichero_server.db.storage import resolve_source
from fichero_server.maintenance import package_paths
from fichero_server.models import DocType, Document, FileType

OLD = "/Volumes/Old Mac/Fichero Projects/article.fichero"


def _doc(db, path, **meta):
    doc = Document(name="p", path=path, doc_type=DocType.file, file_type=FileType.image, metadata=meta)
    db.save(doc)
    return doc


def _own_file(package):
    own = package / "files" / "62" / "fcd61f1a_page.png"
    own.parent.mkdir(parents=True)
    own.write_bytes(b"png")
    return own


def test_an_absolute_path_into_an_earlier_location_becomes_relative(db, test_package, app_db):
    _own_file(test_package)
    doc = _doc(db, f"{OLD}/files/62/fcd61f1a_page.png", source_path=f"{OLD}/files/62/fcd61f1a_page.png")
    done = package_paths.relativize_on_open(db)
    assert done["rewritten"] == [doc.id]
    kept = db.get(Document, doc.id)
    assert kept.id == doc.id and kept.path == "files/62/fcd61f1a_page.png"
    assert kept.metadata["source_path"] == "files/62/fcd61f1a_page.png"
    assert resolve_source(kept, library_root=test_package) is not None


def test_it_is_idempotent_and_audited_once(db, test_package, app_db):
    _own_file(test_package)
    doc = _doc(db, f"{OLD}/files/62/fcd61f1a_page.png")
    package_paths.relativize_on_open(db)
    assert package_paths.relativize_on_open(db)["rewritten"] == []
    assert db.get(Document, doc.id).path == "files/62/fcd61f1a_page.png"
    audits = [a for a in app_db.list_action_audits() if a.action_name == "repair.package-files-relative"]
    assert len(audits) == 1 and doc.id in audits[0].target_ids


def test_a_linked_original_and_a_missing_tail_keep_their_paths(db, test_package, app_db):
    _own_file(test_package)
    linked = _doc(db, "/Volumes/Archive/scans/page1.png")
    missing = _doc(db, f"{OLD}/files/99/not_here.png")
    other = _doc(db, "/Volumes/Archive/other.fichero/files/62/fcd61f1a_page.png")  # another package's file, same tail
    package_paths.relativize_on_open(db)
    assert db.get(Document, linked.id).path == "/Volumes/Archive/scans/page1.png"
    assert db.get(Document, missing.id).path == f"{OLD}/files/99/not_here.png"
    assert db.get(Document, other.id).path.endswith("other.fichero/files/62/fcd61f1a_page.png") is False  # tail exists here: it is ours


def test_a_package_moved_to_another_path_opens_with_relative_paths(db, test_package, app_db, tmp_path):
    _own_file(test_package)
    doc = _doc(db, f"{test_package}/files/62/fcd61f1a_page.png")
    db_manager.close_all()
    moved = tmp_path / "elsewhere" / "article_copy.fichero"
    moved.parent.mkdir()
    shutil.move(str(test_package), str(moved))
    reopened = db_manager.get_database(moved)
    kept = reopened.get(Document, doc.id)
    assert kept.path == "files/62/fcd61f1a_page.png", "the open migration did not run"
    assert resolve_source(kept, library_root=moved) == (moved / "files/62/fcd61f1a_page.png").resolve()
    db_manager.close_all()
    shutil.move(str(moved), str(test_package))
