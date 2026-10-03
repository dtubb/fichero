"""A Kraken training set made from a project's pages (#5398, `compute.tune.input-is-a-training-set`).

The distillation loop: Kraken finds a page's lines, a teacher model (Gemini) reads each line, and a
Kraken reader is fine-tuned on those readings. The set is PAGE XML beside each photograph, as
`ketos train -f page` reads it. Built here through `format.import` of a real Spanish notarial PAGE
page (the corpus fixture), whose pass is then marked as read by the teacher.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.segments import SegmentPass
from fichero_server.training.kraken_set import (
    MANIFEST,
    EmptyTrainingSet,
    export_training_set,
    read_lines,
)

PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
TEACHER = "google/gemini-3-flash-preview"
BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, tmp_path, name: str, folder: Document, *, read_by: str | None = TEACHER) -> Document:
    photo = tmp_path / "photos" / f"{name}.jpg"
    photo.parent.mkdir(exist_ok=True)
    Image.new("RGB", (40, 30), (220, 220, 210)).save(photo)
    doc = Document(name=f"{name}.jpg", doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                   parent_id=folder.id, status=Status.completed)
    db.save(doc)
    if read_by is not None:
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(PAGE)}, BOOT)
        (made,) = db.query(SegmentPass, document_id=doc.id)
        made.model = read_by
        db.save(made)
    return doc


@pytest.fixture
def notebook(db, tmp_path):
    folder = Document(name="SM_NPQ_C09", doc_type=DocType.folder)
    db.save(folder)
    return folder


def test_each_page_is_page_xml_beside_its_photograph(db, tmp_path, notebook):
    """WHY: `ketos train -f page` finds a line's picture through the PAGE file's imageFilename,
    relative to the file. The XML must be Fichero's own export of the teacher's pass, and the photo
    must sit beside it under the name the XML gives, or the trainer silently learns nothing."""
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    out = tmp_path / "set"
    made = export_training_set(db, scope_ids=[notebook.id], teacher=TEACHER, held_out_ids=[], out_dir=out)

    (entry,) = made.pages
    xml = (out / entry.xml).read_text(encoding="utf-8")
    assert f'imageFilename="{entry.image}"' in xml and (out / entry.image).is_file()
    assert entry.document_id == page.id and entry.lines == read_lines(xml) > 0


def test_held_out_pages_are_never_written(db, tmp_path, notebook):
    """WHY: the held-out pages are the test (Fable's ten checked C01 pages). One that leaked into the
    training set would make every score on it meaningless."""
    kept = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    test = _page(db, tmp_path, "SM_NPQ_C09_002", notebook)
    out = tmp_path / "set"
    made = export_training_set(db, scope_ids=[notebook.id], teacher=TEACHER, held_out_ids=[test.id], out_dir=out)

    assert [p.document_id for p in made.pages] == [kept.id]
    assert made.held_out == [{"document_id": test.id, "name": test.name}]
    assert not list(out.glob("SM_NPQ_C09_002*"))


def test_a_page_without_the_teachers_pass_is_listed_with_why(db, tmp_path, notebook):
    """WHY: a page read by another model (or not yet read) must not train the student as if the
    teacher had read it, and must not vanish either: it is listed, with the reason."""
    _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    other = _page(db, tmp_path, "SM_NPQ_C09_002", notebook, read_by="apple-vision")
    unread = _page(db, tmp_path, "SM_NPQ_C09_003", notebook, read_by=None)
    made = export_training_set(db, scope_ids=[notebook.id], teacher=TEACHER, held_out_ids=[],
                               out_dir=tmp_path / "set")

    assert {m["document_id"] for m in made.missing} == {other.id, unread.id}
    assert all(TEACHER in m["why"] for m in made.missing)


def test_the_manifest_crosses_no_path_and_says_who_read_the_lines(db, tmp_path, notebook):
    """WHY: the set is sent to Hugging Face. No path from this Mac may cross (it names a person's
    folders), and a set read by a model must say so in numbers, so the model it trains is never
    mistaken for one taught by a person (`compute.tune.bootstrapped-data-is-marked`)."""
    _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    out = tmp_path / "set"
    made = export_training_set(db, scope_ids=[notebook.id], teacher=TEACHER, held_out_ids=[], out_dir=out)

    text = (out / MANIFEST).read_text(encoding="utf-8")
    assert str(tmp_path) not in text
    manifest = json.loads(text)
    assert manifest["teacher"] == TEACHER
    assert manifest["lines_read_by_a_model"] == made.lines > 0 and manifest["lines_checked_by_a_person"] == 0


def test_nothing_to_train_on_is_refused(db, tmp_path, notebook):
    """WHY: a job sent with an empty set would spend GPU time and money to train on nothing."""
    _page(db, tmp_path, "SM_NPQ_C09_001", notebook, read_by=None)
    with pytest.raises(EmptyTrainingSet):
        export_training_set(db, scope_ids=[notebook.id], teacher=TEACHER, held_out_ids=[], out_dir=tmp_path / "set")
