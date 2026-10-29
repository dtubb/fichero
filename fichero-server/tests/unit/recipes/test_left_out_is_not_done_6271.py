"""A page the step leaves out as blank is not "already done" (#6271), to the spec
`source.recipe.left-out-is-not-done`.

WHY: on 2026.10.27 b18 a recipe run on 874 pages sent find-lines + read-a-line to 329. The other 545 were judged blank
before Kraken ran; with every remaining page left out the step said "already done on every page", and a page with no
lines and no readings looked done. Left out is its own word: counted, named, and never "done"."""

from __future__ import annotations

from fichero_server.finddocs import job as finddocs_job
from fichero_server.recipes import runner
from tests.unit.recipes.test_find_documents_step import _project


def _run(db, card, ids):
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=ids, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    return runner.run(db, subject)["steps"][0]


def test_every_page_left_out_as_blank_is_not_said_to_be_already_done(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = sorted(finddocs_job.blank_versos(db, list(ids.values())))
    assert versos
    sent: list = []
    monkeypatch.setattr(runner, "_run_workflow",
                        lambda db_, card, documents, parent, adopt=None: (sent.append(documents), ("thread", "done", None))[1])
    card = {"steps": ["find-lines"], "job": "find-lines", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["images"], "gives": ["lines"]}

    step = _run(db, card, versos)

    assert not sent  # nothing blank is sent to Kraken
    assert "already done" not in (step.get("why") or "")
    assert "blank" in (step.get("why") or "") and str(len(versos)) in step["why"]
    assert {e["page_id"] for e in step["left_out"]} == set(versos)


def test_the_plan_says_how_many_pages_it_leaves_out_as_blank(client, db, tmp_path):
    from fichero_server.recipes import done
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    every = list(ids.values())
    versos = finddocs_job.blank_versos(db, every)
    from fichero_server.recipes import sorting
    sorting.kinds(db, every, [])  # an earlier run sorted them
    card = {"steps": ["find-lines"], "job": "find-lines", "card": "workflow", "workflow_id": "w", "model_override": None}
    plan = {"runs": [card]}
    done.annotate(db, plan, within=set(every))
    assert f"{len(versos)} left out as blank" in card["note"] and "runs on all" not in card["note"]


def _blank_run(db, tmp_path, monkeypatch, by, redo):
    """Run find-lines over the blank versos, each marked blank `by`; returns (pages sent, the step)."""
    from fichero_server.models import Document
    from fichero_server.recipes import sorting
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = sorted(finddocs_job.blank_versos(db, list(ids.values())))
    for pid in versos:
        doc = db.get(Document, pid)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: by}
        db.save(doc)
    sent: list = []
    monkeypatch.setattr(runner, "_run_workflow",
                        lambda db_, card, documents, parent, adopt=None: (sent.append(list(documents)), ("thread", "done", None))[1])
    card = {"steps": ["find-lines"], "job": "find-lines", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["images"], "gives": ["lines"]}
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=versos, started_by="owner", redo=redo)
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    return versos, sent, runner.run(db, subject)["steps"][0]


def test_a_redo_reads_the_pages_sorting_called_blank(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from fichero_server.recipes import sorting

    versos, sent, _step = _blank_run(db, tmp_path, monkeypatch, sorting.BY_SORTING, ["find-lines"])

    assert sent and set(sent[0]) == set(versos)


def test_a_redo_still_leaves_out_a_page_a_person_called_blank(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from fichero_server.recipes import sorting

    versos, sent, step = _blank_run(db, tmp_path, monkeypatch, sorting.BY_PERSON, ["find-lines"])

    assert not sent
    assert {e["page_id"] for e in step["left_out"]} == set(versos)


def test_a_normal_run_leaves_sorting_blank_pages_out_and_says_so(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from fichero_server.recipes import sorting

    versos, sent, step = _blank_run(db, tmp_path, monkeypatch, sorting.BY_SORTING, [])

    assert not sent and {e["page_id"] for e in step["left_out"]} == set(versos)


def _give_lines(db, doc_id):
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor

    pas = SegmentPass(document_id=doc_id, name="lines", provenance_kind=ProvenanceKind.workflow)
    db.save(pas)
    anchor = SourceAnchor(document_id=doc_id, rect=[0.1, 0.1, 0.6, 0.1])
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    db.save(Segment(document_id=doc_id, pass_id=pas.id, kind="line", anchor=anchor, bbox_x=x, bbox_y=y, bbox_w=w,
                    bbox_h=h, tile=tile, doc_kind=f"{doc_id}:line", provenance_kind=ProvenanceKind.workflow))


def test_a_page_with_live_lines_is_never_blank_and_a_sorting_blank_goes(db, tmp_path):
    """A redo of find-lines lined a sorting-blank page; read-a-line must not drop it again (#6271)."""
    from fichero_server.models import Document
    from fichero_server.recipes import sorting
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = sorted(finddocs_job.blank_versos(db, list(ids.values())))
    sorted_blank, person_blank = versos[0], versos[1]
    for pid, by in ((sorted_blank, sorting.BY_SORTING), (person_blank, sorting.BY_PERSON)):
        doc = db.get(Document, pid)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: by}
        db.save(doc)
        _give_lines(db, pid)

    kinds = sorting.kinds(db, [sorted_blank, person_blank], [])

    assert kinds.get(sorted_blank) != sorting.BLANK
    assert sorting.KIND not in (db.get(Document, sorted_blank).attributes or {})
    assert kinds[person_blank] == sorting.BLANK  # a person's call is never touched
    assert db.get(Document, person_blank).attributes[sorting.SET_BY] == sorting.BY_PERSON


def test_a_redo_of_find_lines_then_read_a_line_reads_the_page_and_the_next_run_keeps_it(
        client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    from fichero_server.recipes import sorting

    versos, sent, _step = _blank_run(db, tmp_path, monkeypatch, sorting.BY_SORTING, ["find-lines"])
    for pid in versos:
        _give_lines(db, pid)  # find-lines found writing there
    sent.clear()
    card = {"steps": ["read-a-line"], "job": "read-a-line", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["lines"], "gives": ["readings"]}
    job_id = runner.enqueue(db, {"runs": [card], "skipped": []}, documents=versos, started_by="owner")
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    step = runner.run(db, subject)["steps"][0]

    assert sent and set(sent[0]) == set(versos)
    assert not step.get("left_out")
