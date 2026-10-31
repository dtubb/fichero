"""A reading field the artifact's provenance replaced gets its reading's text back, in the background, once (#6320)."""
import time

from fichero_server.db import db_manager
from fichero_server.execution import jobs
from fichero_server.maintenance import image_marker_repair as repair
from fichero_server.models import Artifact, DocType, Document, FileType

REAL = {"image_read": "original", "episode_id": "ep_1"}


def _page(db, metadata, *artifacts):
    page = Document(name="p", path="/p.jpg", doc_type=DocType.page, file_type=FileType.image, metadata=metadata)
    db.save(page)
    for kind, text in artifacts:
        db.save(Artifact(document_id=page.id, artifact_type=kind, content=text, provider="x", model="y"))
    return page


def test_every_shape_a_run_wrote_is_put_back_and_nothing_else_is_touched(db):
    page = _page(db, {"description": dict(REAL), "caption": {"episode_id": "ep_2"}, "doc_type": {"image_read": "original"},
                      "keywords": {"a": 1}, "note": "typed by a person", "colors": dict(REAL)},
                 ("description", "A harbour."), ("caption", "Harbour at dusk"), ("classification", "letter"))
    assert repair.repair_document(db, page.id) == (3, 1)  # colors has no reading: left
    meta = db.get(Document, page.id).metadata
    assert meta["description"] == "A harbour." and meta["caption"] == "Harbour at dusk" and meta["doc_type"] == "letter"
    assert meta["colors"] == REAL and meta["keywords"] == {"a": 1} and meta["note"] == "typed by a person"
    assert repair.repair_document(db, page.id) == (0, 1)  # idempotent


def test_a_page_with_nothing_to_put_back_is_not_saved(db, monkeypatch):
    page = _page(db, {"colors": dict(REAL)})
    saved = []
    monkeypatch.setattr(db, "save", lambda row: saved.append(row))
    assert repair.repair_document(db, page.id) == (0, 1) and saved == []


def test_the_open_only_queues_the_job_and_the_job_repairs_once_and_says_what_it_left(tmp_path):
    package = tmp_path / "Dev Project.fichero"
    db = db_manager.get_database(package, create=True)
    fixed = _page(db, {"description": dict(REAL)}, ("description", "A harbour."))
    left = _page(db, {"caption": dict(REAL)})
    # the creating open already ran the job over an empty library: make this the library as it was before the fix
    db.execute("DELETE FROM librarysettings WHERE id = ?", [repair.DONE_SETTING])
    db.execute("DELETE FROM jobs WHERE kind = ?", [repair.KIND])
    db_manager.close_database(package)

    db = db_manager.get_database(package)
    try:
        for _ in range(300):  # the engine's own scheduler runs it; the open did not
            if repair.is_done(db):
                break
            time.sleep(0.1)
        else:
            repair.run(db, repair.SUBJECT)  # a scheduler held back by the suite: run it by hand
        assert repair.is_done(db)
        assert db.get(Document, fixed.id).metadata["description"] == "A harbour."
        assert db.get(Document, left.id).metadata["caption"] == REAL
    finally:
        db_manager.close_database(package)

    db = db_manager.get_database(package)
    try:
        assert repair.is_done(db) and repair.queue_if_needed(db) is None
    finally:
        db_manager.close_database(package)


def test_the_finished_job_row_says_how_many_were_put_back_and_how_many_could_not_be(db):
    job_id = "repair-reading-fields-test"
    jobs._record(db, job_id, kind="workflow", subject=job_id, parent_id=None, state="done", reason="", name="Repair")
    assert repair.finish(db, job_id, 1, 1)["said"]
    reason = jobs.read_job(db, job_id)["reason"]
    assert "1 reading field put back" in reason and "1 could not be" in reason
