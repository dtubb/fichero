"""The Catalogue's plan does not read the line boxes of every page under a folder (the Air, 2026-10-30, 16:27: `folders_to_describe`
-> `_below` -> SELECT *, the third read to fail a recipe start at the cap)."""
from __future__ import annotations

from fichero_server.db import Database
from fichero_server.models import DocType, Document
from fichero_server.recipes import catalogue_step


def test_below_reads_no_metadata_and_covers_the_same(tmp_path):
    db = Database(tmp_path / "fichero.duckdb")
    box = Document(name="box", doc_type=DocType.folder)
    folder = Document(name="folder", doc_type=DocType.folder, parent_id=box.id)
    blank = Document(name="blank", doc_type=DocType.file, parent_id=folder.id)
    pages = [Document(name=f"p{n}", doc_type=DocType.file, parent_id=folder.id, sequence=n, page_content=f"text {n}",
                      metadata={"lines": [{"id": "1"}]}) for n in range(3)]
    for doc in (box, folder, blank, *pages):
        db.save(doc)
    folders, leaves = catalogue_step._below(db, box.id)
    assert [f.id for f in folders] == [folder.id]
    assert {d.id for d in leaves} == {d.id for d in (blank, *pages)}
    assert not any(hasattr(d, "metadata") for d in leaves)
    stored = [db.get(Document, d.id) for d in leaves]
    assert catalogue_step.coverage(leaves) == catalogue_step.coverage(stored)  # a saved `covers` still matches: no model rerun
    db.close()
