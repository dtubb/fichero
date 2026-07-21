"""Saved image edits are the working source, never the provenance source (#3218)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from fichero.api.routes import storage as storage_routes
from fichero.export_service import export_markdown_folder
from fichero.models import DocType, Document, FileType, ImageEditChain
from fichero.db.storage import ensure_thumbnail, resolve_edited_source, resolve_source


def _edited_document(db) -> Document:
    source = db.path.parent / "files" / "source.png"
    source.parent.mkdir(exist_ok=True)
    Image.new("RGB", (20, 10), "red").save(source)
    doc = Document(name="source.png", path=str(source), file_type=FileType.image)
    db.save(doc)
    db.save(
        ImageEditChain(
            document_id=doc.id,
            operations=[{"op": "crop", "page": 1, "params": {"left": 0, "top": 0, "width": 8, "height": 10}}],
        )
    )
    return doc


def test_edited_source_drives_export_and_thumbnail_but_not_raw_source(db, tmp_path):
    root = Document(name="root", doc_type=DocType.folder)
    db.save(root)
    doc = _edited_document(db)
    doc.parent_id = root.id
    db.save(doc)

    edited = resolve_edited_source(doc, db)
    assert edited and Image.open(edited).size == (8, 10)
    assert Image.open(resolve_source(doc, library_root=db.path.parent)).size == (20, 10)

    thumbnail = ensure_thumbnail(doc, package_path=db.path.parent, db=db)
    assert thumbnail and Image.open(thumbnail).size == (8, 10)
    result = export_markdown_folder(db, tmp_path / "export", target_id=root.id)
    asset = Path(result.assets[0].path)
    assert Image.open(asset).size == (8, 10)


def test_no_edit_chain_returns_raw_source(db):
    doc = _edited_document(db)
    db.delete(next(iter(db.query(ImageEditChain, document_id=doc.id))))
    assert resolve_edited_source(doc, db) == resolve_source(doc, library_root=db.path.parent)


def test_storage_source_endpoint_keeps_raw_source(db):
    doc = _edited_document(db)
    response = asyncio.run(
        storage_routes.get_source_file(
            doc.id, db=db, x_fichero_library_path=str(db.path.parent)
        )
    )
    assert Path(response.path) == resolve_source(doc, library_root=db.path.parent)
