"""#5808 (b): the samples the stage page shows are the person's own pages, marked as his, with whether a thumbnail is
made, so the page can draw them (and never mistake the shipped example image for one of them)."""
from __future__ import annotations

from pathlib import Path

from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import samples


def _page(db, tmp_path, name):
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", (8, 8), "white").save(path)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def test_every_proposed_sample_is_marked_as_his_and_says_whether_it_has_a_thumbnail(db, tmp_path):
    for n in range(4):
        _page(db, tmp_path, f"IMG_{n}.png")
    pages = samples.chosen(db)["pages"]
    assert pages and all(p["yours"] is True for p in pages)
    assert all(isinstance(p["thumbnail"], bool) for p in pages)


def test_a_page_the_person_chose_is_his_too(db, tmp_path):
    doc = _page(db, tmp_path, "IMG_9.png")
    samples.choose(db, [doc.id])
    page = samples.chosen(db)["pages"][0]
    assert page["id"] == doc.id and page["yours"] is True


def test_the_response_model_carries_the_fields():
    from fichero_server.api.routes.system.recipes import SamplePage

    assert {"yours", "thumbnail"} <= set(SamplePage.model_fields)
