"""A step that may leave no trace on a page notes the page on the RUN as it finishes it, so a Stop or an engine's death keeps it
(review ## 1134 / ## 1136; `source.recipe.done-is-not-redone`): Names (a page with no names), Leave Out (a page with nothing to leave
out, noted with the line pass it judged, so lines found again are judged again) and Translate/normalise (the reading it writes).
The note is on the run's job detail (`ran_on`), never on the page: the page's own attributes are the person's."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.recipes import done, leave_out, runner
from fichero_server.recipes.done import split_done
from tests.unit.recipes.test_leave_out import _page, _page_with_a_bed_line, _segment

NAMES = {"steps": ["names"], "job": "find-names-tag-words", "card": "workflow", "workflow": "w", "workflow_id": "w",
         "takes": ["text"], "gives": ["entities"]}
LEAVE = {"steps": ["leave"], "job": "leave-out", "card": "leave-out", "takes": ["lines"], "gives": ["lines"]}


def _image(db, name):
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{name}", status=Status.completed)
    db.save(doc)
    return doc


def _stopped_after_the_first_page(monkeypatch, db, card, pages, key_of):
    """A run whose step notes the first page and is then stopped: its row ends cancelled."""
    def stopped(db_, card_, documents, kinds, job_id, scratch, started_by, adopt=None):
        done.page_finished(db_, job_id, key_of(documents[0]))
        return None, "cancelled", "Stopped by you"

    monkeypatch.setattr(runner, "_run_card", stopped)
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=pages, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    runner.run(db, subject)
    db.execute("UPDATE jobs SET state = 'cancelled' WHERE id = ?", [job_id])
    return job_id


def test_page_finished_notes_on_the_run_and_with_no_run_does_nothing(db):
    seen: list[str] = []
    done.page_finished(db, None, "p")
    done.page_finished(db, "no-such-run", "p")
    done.NOTES["run-x"] = seen.append
    try:
        done.page_finished(db, "run-x", "p1")
    finally:
        done.NOTES.pop("run-x")
    assert seen == ["p1"]


def test_names_stopped_after_a_page_with_no_names_keeps_that_page_done_and_the_page_untouched(db, jobs_run_by_the_test,
                                                                                               monkeypatch):
    first, second = _image(db, "a.jpg"), _image(db, "b.jpg")
    before = dict(db.get(Document, first.id).attributes or {})
    _stopped_after_the_first_page(monkeypatch, db, NAMES, [first.id, second.id], lambda page: page)
    assert split_done(db, NAMES, [first.id, second.id]) == ([second.id], 1)
    assert dict(db.get(Document, first.id).attributes or {}) == before, "the page's own attributes are the person's"


def test_a_run_that_is_resumed_skips_what_it_noted_before_it_ended(db):
    first, second = _image(db, "a.jpg"), _image(db, "b.jpg")
    assert split_done(db, NAMES, [first.id, second.id], own={first.id}) == ([second.id], 1)


def test_leave_out_notes_each_page_with_the_pass_it_judged_even_with_nothing_to_leave_out(db, monkeypatch):
    clean = _image(db, "clean.jpg")
    for ln in _page():
        db.save(_segment(clean.id, ln))
    bed, _ = _page_with_a_bed_line(db)
    notes: list[str] = []
    done.NOTES["run-1"] = notes.append
    monkeypatch.setattr("fichero_server.llm.working_lines.working_lines",
                        lambda db_, doc_id, **kw: SimpleNamespace(pass_row=SimpleNamespace(id="pass-1")))
    try:
        leave_out.leave_out_pages(db, [clean.id, bed.id], "run-1")
    finally:
        done.NOTES.pop("run-1")
    assert notes == [f"{clean.id}@pass-1", f"{bed.id}@pass-1"]


def test_lines_found_again_after_leave_out_are_judged_again_not_skipped_forever(db, jobs_run_by_the_test, monkeypatch):
    first, second = _image(db, "a.jpg"), _image(db, "b.jpg")
    current = {"pass": "pass-1"}
    monkeypatch.setattr("fichero_server.llm.working_lines.working_lines",
                        lambda db_, doc_id, **kw: SimpleNamespace(pass_row=SimpleNamespace(id=current["pass"])))
    _stopped_after_the_first_page(monkeypatch, db, LEAVE, [first.id, second.id], lambda page: done.judged_key(db, page))
    assert "leave-out" in done.KNOWS_DONE
    assert split_done(db, LEAVE, [first.id, second.id]) == ([second.id], 1), "judged on its pass: done, not every page"
    current["pass"] = "pass-2"  # Find Lines ran again on the page: a new pass
    assert split_done(db, LEAVE, [first.id, second.id]) == ([first.id, second.id], 0), "a new pass is judged"


def test_translate_is_done_on_a_page_that_holds_its_reading_by_its_model(db):
    page, other = _image(db, "t.jpg"), _image(db, "u.jpg")
    card = {"job": "translate-transliterate-normalise", "model_override": "gpt-5",
            "tool_config": {"analyze": {"reading_kind": "transcription", "reading_level": "regularised"}}}
    assert "translate-transliterate-normalise" in done.KNOWS_DONE
    assert split_done(db, card, [page.id, other.id]) == ([page.id, other.id], 0)
    db.save(Artifact(document_id=page.id, artifact_type="regularised", model="gpt-5", provider="openai"))
    db.save(Artifact(document_id=other.id, artifact_type="regularised", model="another", provider="openai"))
    assert split_done(db, card, [page.id, other.id]) == ([other.id], 1), "another model's reading is not this step's"
    translation = {**card, "tool_config": {"analyze": {"reading_kind": "translation", "reading_level": None}}}
    assert split_done(db, translation, [page.id])[0] == [page.id], "a level is not a translation"
