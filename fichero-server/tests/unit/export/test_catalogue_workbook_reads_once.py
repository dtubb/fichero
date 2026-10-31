"""catalogue.export.streams-at-scale (the part that needs no batching): a workbook reads the documents once and works out each
folder's Problemas once, not once per column or per sheet."""
from fichero_server import catalogue_sheet as sheet
from fichero_server.models import Document
from fichero_server.recipes import catalogue_step
from tests.unit.export.helpers import folder, page


def _box(db, n):
    box = folder(db, "Caja", proto="eap_box")
    for i in range(n):
        f = folder(db, f"Doc {i}", box.id, seq=i, attrs={"catalogue_title": f"Título {i}"})
        page(db, f"IMG_{i:03}.jpg", f.id, seq=1)
    return box


def test_problems_are_worked_out_once_per_folder(db, monkeypatch):
    box = _box(db, 4)
    seen: list[str] = []
    real = catalogue_step.date_problems
    monkeypatch.setattr(catalogue_step, "date_problems", lambda doc: seen.append(doc.id) or real(doc))
    sheet.workbook(db, box)
    assert len(seen) == len(set(seen)) == 4


def test_no_folder_is_listed_by_a_query_of_its_own(db, monkeypatch):
    box = _box(db, 4)
    by_parent: list[str] = []
    real = db.query

    def query(model, **filters):
        if model is Document and "parent_id" in filters:
            by_parent.append(filters["parent_id"])
        return real(model, **filters)

    monkeypatch.setattr(db, "query", query)
    sheet.workbook(db, box)
    assert by_parent == []


def test_the_reads_are_gone_after_the_workbook(db):
    box = _box(db, 1)
    sheet.workbook(db, box)
    assert sheet._READS.get() is None
    assert [d.name for d in sheet._children(db, box.id)] == ["Doc 0"]
