"""What has been run on a document, in one read for many (#5434, `activity.document.what-has-been-run`).

WHY: a person could see what a run made, never what had been run on a page: which reader read it,
whether its names were read, what failed. The library table's Done column and the Inspector's "What
has been run" both need it, for the visible rows at once, never one call per row. It is built from
the job rows named after the document and the runs recorded on it, as recorded when they ran.
"""
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.models import DocType, Document, FileType


def _page(db, name, **kw):
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, **kw)
    db.save(doc)
    return doc


def test_one_read_lists_each_documents_runs_newest_first(client, db):
    jobs.set_paused(True)  # rows only: nothing runs
    try:
        first = _page(db, "p1.jpg", workflow_runs=[{
            "workflow_id": "wf-read", "workflow_name": "Read the page", "provider": "anthropic",
            "model": "claude-x", "thread_id": "t1", "started_at": "2026-10-01T10:00:00+00:00",
            "completed_at": "2026-10-01T10:05:00+00:00"}])
        second = _page(db, "p2.jpg")
        untouched = _page(db, "p3.jpg")
        thumb = jobs.enqueue(db, "thumbnail", first.id)
        jobs.cancel_job(db, thumb)
        names = jobs.enqueue(db, "nlp-draft", second.id)

        r = client.get("/api/documents/run-history",
                       params=[("ids", first.id), ("ids", second.id), ("ids", untouched.id), ("ids", "gone")])
        assert r.status_code == 200, r.text
        items = r.json()["items"]

        assert set(items) == {first.id, second.id, untouched.id}  # an unknown id is left out
        assert items[untouched.id] == []
        [made] = items[second.id]
        assert (made["kind"], made["state"], made["job_id"], made["source"]) == ("nlp-draft", "waiting", names, "job")
        assert made["name"] == jobs.kind_name("nlp-draft")

        kinds = [(e["source"], e["kind"], e["state"]) for e in items[first.id]]
        assert kinds == [("job", "thumbnail", "cancelled"), ("workflow_run", "workflow", "done")]  # newest first
        run = items[first.id][1]
        assert (run["model"], run["provider"], run["name"], run["cost"]) == ("claude-x", "anthropic", "Read the page", None)
        assert run["at"].startswith("2026-10-01T10:05:00")
    finally:
        jobs.set_paused(False)
