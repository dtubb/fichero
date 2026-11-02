"""`wide.review.accept-line-and-all` (#5720; owner ruling 2026-11-02): a review's readings count at once; "Accept all N" confirms them
as one action (`reading.choose_many`) with one undo for the page. Only a person may (the action layer's rule), a line whose counting
reading is not a review's is left alone, and a page with nothing waiting is refused in words."""
from __future__ import annotations

from fichero_server.llm.working_lines import write_readings
from fichero_server.models import Artifact, ReadingChoice
from tests.unit.api.test_compare_pick_5900 import _lines
from tests.unit.training.test_kraken_training_set import _page, notebook  # noqa: F401  (the fixture)


def _reviewed(db, tmp_path, notebook, how_many=2):  # noqa: F811
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    lines = _lines(db, page)[:how_many]
    review = Artifact(document_id=page.id, artifact_type="transcription_review", content="x")
    db.save(review)
    write_readings(db, document_id=page.id, readings=[(s.id, f"revisada {i}", None) for i, s in enumerate(lines)],
                   artifact_id=review.id, run_id="run-r", level="as_written", library_path=None, derived_from={})
    return page, lines


def _live(db, segment):
    return [c for c in db.query(ReadingChoice, segment_id=segment.id) if c.superseded_at is None]


def _accept(client, page):
    return client.post("/api/actions/invoke", json={"name": "reading.choose_many", "params": {"document_id": page.id}})


def test_accept_all_chooses_every_reviewed_line_and_one_undo_puts_them_back(client, db, tmp_path, notebook):  # noqa: F811
    page, lines = _reviewed(db, tmp_path, notebook)
    assert all(not _live(db, s) for s in lines)
    done = _accept(client, page)
    assert done.status_code == 200, done.text
    assert len(done.json()["result"]["items"]) == 2 and all(len(_live(db, s)) == 1 for s in lines)

    undone = client.post(f"/api/actions/audit/{done.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    assert all(not _live(db, s) for s in lines)  # one step, every line back to no choice


def test_a_page_with_nothing_waiting_is_refused_in_words_and_a_second_accept_is_too(client, db, tmp_path, notebook):  # noqa: F811
    page = _page(db, tmp_path, "SM_NPQ_C09_001", notebook)
    refused = _accept(client, page)
    assert refused.status_code == 409 and "review's reading" in refused.text
    page, _ = _reviewed(db, tmp_path, notebook)
    assert _accept(client, page).status_code == 200
    assert _accept(client, page).status_code == 409  # nothing left to confirm
