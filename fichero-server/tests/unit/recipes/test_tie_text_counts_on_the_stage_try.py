"""`wide.nomodel.tie-figures-on-his-pages` engine half (#5721, #5720): the Read try runs the tie on its copy and the
result carries the tie's counts, in the project's own page ids, so Set Up can show them under the tie row."""
from __future__ import annotations

from fichero_server.execution import jobs
from tests.unit.recipes.test_stage_try_words_5687 import _pages, _run, _set_up


def test_wide_the_read_try_carries_the_ties_counts_per_page(client, db, tmp_path, monkeypatch, jobs_run_by_the_test):
    from fichero_server.checking import tie_text
    from fichero_server.recipes import runner

    pages = _pages(db, tmp_path, 2)
    _set_up(client, ["read-a-line", "tie-text-to-lines"])
    monkeypatch.setattr(runner, "_run_workflow", lambda *a, **k: (None, "done", None))  # the reader's own run is not under test
    tied_on = []

    def fake_tie(copy_db, job_id, request, started_by):
        tied_on.append(list(request.scope_ids))
        first, second = request.scope_ids
        counts = dict.fromkeys(tie_text.COUNTS, 0) | {"tied": 9, "doubtful": 2, "untied": 1, "pages_tied": 1, "drafts": 1}
        return {"counts": counts, "stopped": False, "missing": [], "thresholds": {},
                "flagged": [{"document_id": first, "segment_id": "s1", "flag": tie_text.DOUBTFUL, "score": 0.1},
                            {"document_id": first, "segment_id": "s2", "flag": tie_text.DOUBTFUL, "score": 0.2},
                            {"document_id": second, "flag": tie_text.DRAFT, "score": 0.3}],
                "per_page": {first: {"tied": 9, "doubtful": 2, "untied": 1, "draft": False},
                             second: {"tied": 0, "doubtful": 0, "untied": 0, "draft": True}}}

    monkeypatch.setattr(tie_text, "_tie", fake_tie)

    def wait(copy_db, child, parent):  # the copy's lane runs the tie in the app; the test runs it where it stands
        row = jobs.read_job(copy_db, child)
        jobs.KINDS[row["kind"]].run(copy_db, row["subject"])
        copy_db.execute("UPDATE jobs SET state = 'done' WHERE id = ?", [child])
        return child, "done", None

    monkeypatch.setattr(runner, "_wait", wait)
    started = client.post("/api/recipes/stages/read/try", json={"candidates": []})
    assert started.status_code == 200, started.text
    _run(db, started.json())

    result = client.get("/api/recipes/stages/read/try").json()
    assert result["state"] == "done", result
    assert tied_on and all(len(on) == 2 for on in tied_on), "the tie ran on each candidate's copy of the two pages"
    assert all(c["tie"]["counts"]["tied"] == 9 for c in result["candidates"] if c["state"] == "done"), "each column has its own"
    tie = result["tie"]
    assert tie["counts"]["tied"] == 9 and tie["counts"]["doubtful"] == 2 and tie["counts"]["drafts"] == 1
    ids = {p.id for p in pages}
    assert set(tie["pages"]) == ids, "the per-page counts are keyed by the project's page ids, not the copy's"
    assert sorted(v["draft"] for v in tie["pages"].values()) == [False, True]
    assert sum(v["doubtful"] for v in tie["pages"].values()) == 2
