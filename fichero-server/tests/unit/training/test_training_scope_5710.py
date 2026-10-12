"""Training on a folder looks inside its subfolders, and a set with nothing to teach says why first (#5710).

WHY: a start refused with "no page in scope has a pass read by kraken-mccatmus with read lines (2 missing)" when
both pages had that pass. Its scope was two pages, not the Sources folder, and Sources does reach every page under
it. The two were missing because an engine from before #5699 did not find a copied page's photograph, but the
message's opening blamed the pass, and that sent the diagnosis toward subfolders.
"""

from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from fichero_server.training.kraken_set import TrainingSet, pages_in_scope


def test_a_folder_in_scope_reaches_the_pages_in_its_subfolders(db):
    sources = Document(name="Sources", doc_type=DocType.folder)
    db.save(sources)
    box = Document(name="CACIQUES_INDIOS,17,D.5", doc_type=DocType.folder, parent_id=sources.id)
    db.save(box)
    pages = [Document(name=f"{n}_Hoja.JPG", doc_type=DocType.file, file_type=FileType.image, path=f"/{n}_Hoja.JPG",
                      parent_id=box.id, sort_order=n) for n in (1, 2, 3)]
    for page in pages:
        db.save(page)

    assert [p.id for p in pages_in_scope(db, [sources.id])] == [p.id for p in pages]


def test_an_empty_set_says_why_its_pages_cannot_teach_before_anything_else():
    made = TrainingSet(teacher="kraken-mccatmus")
    made.missing = [{"document_id": d, "name": d, "why": "its photograph is not on this Mac"} for d in ("a", "b")]

    said = made.why_empty()

    assert said.startswith("nothing to train on: none of the 2 pages in scope can teach: "), said
    assert "2 pages: its photograph is not on this Mac" in said
    assert "has a pass read by" not in said, "the pass is not the reason here"
