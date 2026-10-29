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


def _blank_split(db, tmp_path):
    """Two pages sorting called blank and one a person did, on a project of 12 pages; returns (ids, card)."""
    from fichero_server.models import Document
    from fichero_server.recipes import sorting
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    every = list(ids.values())
    versos = sorted(finddocs_job.blank_versos(db, every))
    assert len(versos) >= 3
    for pid, by in zip(versos[:3], (sorting.BY_SORTING, sorting.BY_SORTING, sorting.BY_PERSON)):
        doc = db.get(Document, pid)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: by}
        db.save(doc)
    card = {"steps": ["find-lines"], "job": "find-lines", "card": "workflow", "workflow_id": "w", "model_override": None}
    return every, card


def test_the_plan_note_splits_blank_by_sorting_from_blank_a_person_called(client, db, tmp_path):
    from fichero_server.recipes import done

    every, card = _blank_split(db, tmp_path)
    done.annotate(db, {"runs": [card]}, within=set(every))

    assert "2 left out as blank by sorting (redo them to read anyway); 1 you marked blank" in card["note"], card["note"]


def test_the_estimate_does_not_price_the_blank_pages_a_normal_run_leaves_out(client, db, tmp_path):
    from fichero_server.recipes import done

    every, card = _blank_split(db, tmp_path)
    plan = {"runs": [card]}
    normal = done.todo_counts(db, plan, within=set(every))["find-lines"]
    redo = done.todo_counts(db, plan, within=set(every), redo={"find-lines"}).get("find-lines")

    assert normal == len(every) - 3
    assert redo is None  # a redo is priced on every page it will read, as before


def test_a_redo_of_find_lines_then_read_a_line_in_the_same_run_reads_the_page_and_a_later_run_leaves_it_out(
        client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    """Kraken finds noise lines on a real blank, so lines never make a page not blank; the redo's pages stay in for the
    run's later page steps, and the next normal run leaves them out again as sorting decides."""
    from fichero_server.models import Document
    from fichero_server.recipes import sorting
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = sorted(finddocs_job.blank_versos(db, list(ids.values())))
    for pid in versos:
        doc = db.get(Document, pid)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: sorting.BY_SORTING}
        db.save(doc)
    sent: dict[str, list] = {}
    monkeypatch.setattr(runner, "_run_workflow", lambda db_, card, documents, parent, adopt=None:
                        (sent.setdefault(card["job"], []).append(list(documents)), ("thread", "done", None))[1])
    cards = [{"steps": [job], "job": job, "card": "workflow", "workflow": "w", "workflow_id": "w",
              "provider_override": None, "model_override": None, "takes": ["images"], "gives": ["lines"]}
             for job in ("find-lines", "read-a-line")]

    def go(redo):
        job_id = runner.enqueue(db, {"runs": cards, "skipped": []}, documents=versos, started_by="owner", redo=redo)
        _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
        return runner.run(db, subject)["steps"]

    go(["find-lines"])
    assert set(sent["find-lines"][0]) == set(versos)
    assert sent.get("read-a-line") and set(sent["read-a-line"][0]) == set(versos)

    sent.clear()
    go([])
    assert not sent  # the next normal run leaves them out again


def test_a_redo_of_find_lines_keeps_the_sorting_blank_pages_in_the_note_and_price_of_read_a_line(client, db, tmp_path):
    """The run's later page steps read the pages the redo took in (`detail.blank_bypassed`): their plan note and price
    must not leave them out. A page a person called blank stays out."""
    from fichero_server.recipes import done

    every, find = _blank_split(db, tmp_path)
    read = {"steps": ["read-a-line"], "job": "read-a-line", "card": "workflow", "workflow_id": "w", "model_override": None}
    plan = {"runs": [find, read]}
    done.annotate(db, plan, within=set(every), redo={"find-lines"})

    assert "left out as blank by sorting" not in read["note"], read["note"]
    assert "1 you marked blank" in read["note"] and f"runs on {len(every) - 1} of {len(every)} pages" in read["note"]
    assert done.todo_counts(db, plan, within=set(every), redo={"find-lines"})["read-a-line"] == len(every) - 1
    assert done.todo_counts(db, plan, within=set(every))["read-a-line"] == len(every) - 3  # no redo: left out as before


def test_the_plan_note_still_says_what_is_already_done_when_it_leaves_pages_out(client, db, tmp_path, monkeypatch):
    from fichero_server.recipes import done

    every, card = _blank_split(db, tmp_path)
    monkeypatch.setattr(done, "split_done", lambda db_, card_, pages, memo=None: (pages[2:], 2))
    done.annotate(db, {"runs": [card]}, within=set(every))

    assert card["note"].startswith("already done on 2; runs on "), card["note"]


def test_nothing_to_run_counts_the_done_pages_of_the_whole_run_not_the_last_batch(client, db, tmp_path, jobs_run_by_the_test,
                                                                                    monkeypatch):
    """The step carries two pages done from before this batch (a resumed run's checkpoint) and this batch has only a
    left-out page: 'the rest already done' is true of the run (`total_done`); counting only the batch's own it would
    read 'all 1 page left out'."""
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    one = sorted(ids.values())[0]

    def pages_of(db_, card, step, batch, tree, detail):
        step["already_done"] = 2  # earlier batches', not this one's
        return [], {"left_out": [{"page_id": one}]}, {}

    monkeypatch.setattr(runner, "_step_pages", pages_of)
    card = {"steps": ["find-lines"], "job": "find-lines", "card": "workflow", "workflow": "w", "workflow_id": "w",
            "provider_override": None, "model_override": None, "takes": ["images"], "gives": ["lines"]}

    step = _run(db, card, [one])

    assert step["why"] == "nothing to run: 1 page left out, the rest already done", step["why"]


def test_the_pages_a_redo_took_in_survive_a_resume_of_the_same_run(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    """`detail.blank_bypassed` is saved with the run's detail: a run whose read-a-line step did not finish, resumed,
    still reads the sorting-blank pages the redo of find-lines took in."""
    import json

    from fichero_server.execution import jobs
    from fichero_server.models import Document
    from fichero_server.recipes import sorting
    from tests.unit.finddocs.boxes import istmina_box

    pages = istmina_box()[0][:12]
    _folder, ids = _project(db, tmp_path, pages)
    versos = sorted(finddocs_job.blank_versos(db, list(ids.values())))
    for pid in versos:
        doc = db.get(Document, pid)
        doc.attributes = {sorting.KIND: sorting.BLANK, sorting.SET_BY: sorting.BY_SORTING}
        db.save(doc)
    sent: dict[str, list] = {}
    monkeypatch.setattr(runner, "_run_workflow", lambda db_, card, documents, parent, adopt=None:
                        (sent.setdefault(card["job"], []).append(list(documents)), ("thread", "done", None))[1])
    cards = [{"steps": [job], "job": job, "card": "workflow", "workflow": "w", "workflow_id": "w",
              "provider_override": None, "model_override": None, "takes": ["images"], "gives": ["lines"]}
             for job in ("find-lines", "read-a-line")]
    job_id = runner.enqueue(db, {"runs": cards, "skipped": []}, documents=versos, started_by="owner", redo=["find-lines"])
    _kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    runner.run(db, subject)
    detail = json.loads(jobs.read_job(db, job_id)["detail"])
    assert set(detail["blank_bypassed"]) == set(versos)

    detail["batches_done"], detail["batch_states"] = 0, ["done", None]  # stopped in the batch: read-a-line did not finish
    detail["steps"][1]["state"] = "waiting"
    jobs.save_detail(db, job_id, json.dumps(detail))
    sent.clear()
    runner.run(db, subject)

    assert set(sent["read-a-line"][0]) == set(versos) and "find-lines" not in sent
