"""catalogue.export.recipe-last-step (catalogue-export.md step 2.4): the export card keeps the workbook and the transcripts."""
from fichero_server import kept_export
from fichero_server.recipes import runner
from tests.unit.export.helpers import folder, page


def _card(folder_path, *formats, final=True):
    return {"card": "export", "job": "export", "folder": str(folder_path), "formats": list(formats), "final": final}


def _project(db):
    box = folder(db, "Caja", proto="eap_box")
    f = folder(db, "Doc", box.id, attrs={"catalogue_title": "T"})
    page(db, "IMG_001.jpg", f.id, seq=1)
    return [p.id for p in [f]]


def test_the_last_batch_keeps_both_formats_in_the_cards_folder(db, tmp_path):
    docs = _project(db)
    out = tmp_path / "out"
    out.mkdir()
    assert runner._run_export(db, _card(out, "catalogue-workbook", "word-transcript"), docs) == (None, "done", None)
    kept = {e["format"]: e["per"] for e in kept_export._exports(db)}
    assert kept == {"catalogue-workbook": "document", "word-transcript": "document"}


def test_an_earlier_batch_keeps_nothing_yet(db, tmp_path):
    docs = _project(db)
    out = tmp_path / "out"
    out.mkdir()
    assert runner._run_export(db, _card(out, "catalogue-workbook", final=False), docs)[1] == "done"
    assert kept_export._exports(db) == []


def test_a_second_run_writes_the_same_export_again_not_a_second_one(db, tmp_path):
    docs = _project(db)
    out = tmp_path / "out"
    out.mkdir()
    runner._run_export(db, _card(out, "catalogue-workbook"), docs)
    runner._run_export(db, _card(out, "catalogue-workbook"), docs)
    assert len(kept_export._exports(db)) == 1


def test_no_folder_or_a_folder_that_is_refused_fails_in_a_sentence(db, tmp_path):
    docs = _project(db)
    no_folder = {**_card(tmp_path, "catalogue-workbook"), "folder": None}
    assert runner._run_export(db, no_folder, docs)[1] == "failed"
    state, why = runner._run_export(db, _card(tmp_path / "missing", "catalogue-workbook"), docs)[1:]
    assert state == "failed" and why


def test_the_workbook_line_says_how_many_rows_are_undescribed(db):
    from fichero_server import catalogue_sheet

    box = folder(db, "Caja", proto="eap_box")
    folder(db, "Uno", box.id, seq=1)
    folder(db, "Dos", box.id, seq=2)
    assert catalogue_sheet.undescribed_count(db, None) == (2, 2)
