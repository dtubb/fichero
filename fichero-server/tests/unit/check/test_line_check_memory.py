"""The teacher-line check stopped for memory waits and carries on (#5524).

Sergio C01, 2026-10-06: the check wrote 698 verdicts, then the Kraken memory guard stopped it ('needs about
2.5 GB ... 2.5 GB free') and the run showed failed. A stop for memory now puts the job back to waiting; run
again, it carries on after the last page it finished, so no line gets a second verdict and the counts are
the whole run's. Kraken is faked at its seam, as in `test_line_against_page.py`.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import KrakenMemoryUnavailableError
from fichero_server.models import DocType, Document
from tests.unit.check.test_line_against_page import READER, SIZE, _shift_at
from tests.unit.training.test_kraken_training_set import TEACHER, _page


@pytest.fixture
def two_pages(db, tmp_path, jobs_run_by_the_test):
    folder = Document(name="SM_NPQ_C01", doc_type=DocType.folder)
    db.save(folder)
    pages = [_page(db, tmp_path, f"SM_NPQ_C01_00{i}", folder, size=SIZE) for i in (1, 2)]
    for doc in pages:
        doc.metadata = {**(doc.metadata or {}), "width": SIZE[0], "height": SIZE[1]}
        db.save(doc)
    return folder, pages


def test_a_check_stopped_for_memory_carries_on_without_a_second_verdict(client, db, two_pages, monkeypatch):
    """WHY: re-running the whole check after a memory stop would give every line already checked a second
    'reject' verdict and count it twice; failing it lost the run. It waits, then finishes the rest once."""
    folder, pages = two_pages
    read: list[str] = []
    calls = []

    def rough_read(image_path, model_path, lines, **kw):
        calls.append(str(image_path))
        if len(calls) == 2:  # the second page, after the first has its verdicts
            raise KrakenMemoryUnavailableError("Waiting: memory is tight: needs about 2.5 GB, 2.4 GB free")
        read.append(str(image_path))
        k = _shift_at(lines)  # one misaligned line a page: one verdict a page
        return [("" if i == k else lines[k]["text"] if i == k + 1 else ln["text"]) for i, ln in enumerate(lines)]

    monkeypatch.setattr(kraken_runtime, "read_given_lines", rough_read)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    r = client.post("/api/check/runs", json={"check": "line-against-page", "provider": "kraken", "model": READER,
                                             "layer": "readings", "scope_ids": [folder.id], "pass_model": TEACHER})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    from fichero_server.checking import job as check_job

    check_job.register_job_kinds()

    with pytest.raises(jobs.JobDeferred, match="memory is tight"):
        jobs._scheduler._work(db, job_id, jobs.KINDS[kind], subject, None)
    jobs._scheduler._work(db, job_id, jobs.KINDS[kind], subject, None)

    assert len(calls) == 3 and calls[1] == calls[2]  # the refused page again, the finished one not
    assert sorted(read) == sorted(p.path for p in pages)  # each page read once
    status = client.get(f"/api/check/runs/{job_id}").json()
    assert status["counts"]["closer_to_a_neighbour"] == 2
    assert len({f["reading_id"] for f in status["flagged"]}) == len(status["flagged"])  # none twice
    assert {f["document_id"] for f in status["flagged"]} == {p.id for p in pages}
    for flag in status["flagged"]:
        verdicts = client.get("/api/check/verdicts", params={"target_id": flag["reading_id"]}).json()["items"]
        assert len(verdicts) == 1
