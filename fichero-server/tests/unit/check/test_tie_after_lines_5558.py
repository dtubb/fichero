"""The tie runs whichever comes first, the page's reading or its lines (`source.job.tie-text-to-lines`, #5558).

A page transcribed whole and THEN segmented (the order met 2026-11-13: Transcribe, then Detect Segments, and every
line read "No reading") queues the same one waiting tie job a page segmented and then transcribed does, and both together
make one. WHY: the tie was queued only from a page reading saved on a page that already had lines, so the other order
left every line untied until someone ran the step by hand.

Driven through the real seams: a reading saved as every reader's result is (`save_file_artifact`), lines saved as Kraken's
segmentation is (a `regions` artifact with boxes, then `convert_new_results`), and the queue read from the jobs table.
"""
# ruff: noqa: F811  (the tie tests' fixtures are imported and named as arguments)
from __future__ import annotations

from fichero_server.checking import tie_text
from fichero_server.maintenance.project_conversion import convert_new_results
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document
from tests.unit.check.test_tie_text_to_lines import READER, reader  # noqa: F401  (pytest fixtures)
from tests.unit.check.test_which_reading_counts_after_the_tie import _install, _save_page_reading, _tie_jobs
from tests.unit.training.test_kraken_training_set import _page

TEXT = "uno dos\ntres cuatro\ncinco seis"


def _bare_page(db, tmp_path):
    folder = Document(name="SM_NPQ_C05", doc_type=DocType.folder)
    db.save(folder)
    return _page(db, tmp_path, "SM_NPQ_C05_001", folder, read_by=None, size=(400, 300))


def _find_lines(db, doc):
    """Kraken's segmentation saved as Find Lines / Detect Segments save it, then the page's own pass made of it."""
    geometry = OCRGeometryResult(provider="kraken", text="", boxes=[
        OCRGeometryBox(text="", bbox=[0.1, 0.1 + 0.2 * i, 0.8, 0.05], level="line") for i in range(3)])
    db.save(Artifact(document_id=doc.id, artifact_type="regions", content="", ocr_geometry=geometry,
                     provider="kraken", model="blla"))
    return convert_new_results(db, doc.id)


def test_a_page_read_whole_and_then_segmented_queues_its_tie(client, db, tmp_path, reader):
    _install(READER)
    doc = _bare_page(db, tmp_path)
    _save_page_reading(db, doc, TEXT)
    assert _tie_jobs(db) == []  # no lines yet: nothing to tie to
    assert _find_lines(db, doc) == "converted"
    ((_id, subject, state, started_by),) = _tie_jobs(db)
    assert (state, started_by) == ("waiting", tie_text.AUTOMATIC) and subject.endswith(doc.id)


def test_a_page_segmented_and_then_read_still_queues_its_tie(client, db, tmp_path, reader):
    _install(READER)
    doc = _bare_page(db, tmp_path)
    assert _find_lines(db, doc) == "converted"
    assert _tie_jobs(db) == []  # lines but no reading: nothing to tie
    _save_page_reading(db, doc, TEXT)
    assert len(_tie_jobs(db)) == 1


def test_both_triggers_together_make_one_job(client, db, tmp_path, reader):
    _install(READER)
    doc = _bare_page(db, tmp_path)
    _save_page_reading(db, doc, TEXT)
    _find_lines(db, doc)
    _save_page_reading(db, doc, TEXT + "!")  # a second reading, on a page that now has lines
    assert len(_tie_jobs(db)) == 1


def test_lines_on_a_page_with_no_reading_queue_nothing(client, db, tmp_path, reader):
    _install(READER)
    doc = _bare_page(db, tmp_path)
    assert _find_lines(db, doc) == "converted"  # lines, and no reading at all
    assert _tie_jobs(db) == []


def test_a_tie_that_cannot_be_queued_says_so_to_its_caller(db, monkeypatch):
    """`_queue_tie` never raises (the lines are saved either way) but answers False, so the page's line in the log
    says the reading was not tied (#5558, #6354: a failure is never only a log line)."""
    from fichero_server.maintenance import project_conversion

    def boom(_db, _doc):
        raise RuntimeError("jobs table is locked")

    monkeypatch.setattr(tie_text, "after_lines", boom)
    assert project_conversion._queue_tie(db, "page-1") is False
    monkeypatch.setattr(tie_text, "after_lines", lambda _db, _doc: None)
    assert project_conversion._queue_tie(db, "page-1") is True
