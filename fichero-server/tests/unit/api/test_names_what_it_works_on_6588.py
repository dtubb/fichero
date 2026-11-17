"""The import's row names what it works on (`activity.pane.names-what-it-works-on`, #6588).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. Acceptance: an import of a folder of images lists ONE top-level row
naming the project and the count, a child per stage (thumbnails, text, embed) with its own count, and under the running
stage the files in flight by name. Through `GET /api/activity/jobs`, the import's queue seeded as an import leaves it.
"""
from __future__ import annotations

import uuid

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import Document, DocType, FileType


def test_the_import_row_names_the_project_the_count_and_its_stages(client, db, test_package, monkeypatch):
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    jobs._ensure(db)
    library = str(test_package)
    derivatives._progress_add(library, 2618)
    try:
        pages = []
        for i in range(3):
            doc = Document(id=str(uuid.uuid4()), name=f"letter-{i:03d}.jpg", doc_type=DocType.file, file_type=FileType.image)
            db.save(doc)
            pages.append(doc)
        now = utc_now().replace(tzinfo=None)

        def job(kind, subject, state):
            db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at) "
                       "VALUES (?, ?, ?, ?, 0, 'import', ?)", [str(uuid.uuid4()), kind, subject, state, now])

        for doc in pages:
            job(derivatives.THUMBNAIL_KIND, doc.id, "done")
        job(derivatives.NLP_KIND, pages[0].id, "running")
        job(derivatives.NLP_KIND, pages[1].id, "waiting")
        job(derivatives.EMBED_KIND, pages[2].id, "waiting")

        listed = client.get("/api/activity/jobs").json()
        (row,) = [j for j in listed["jobs"] if j["task_type"] == "derivatives"]

        project = test_package.stem
        assert row["name"] == f"Prepare pages · {project} · 2,618", "the project and the count, never only its kind"
        stages = {s["stage"]: s for s in row["stages"]}
        assert [s["stage"] for s in row["stages"]] == [derivatives.THUMBNAIL_KIND, derivatives.NLP_KIND,
                                                       derivatives.EMBED_KIND]
        assert (stages["thumbnail"]["done"], stages["thumbnail"]["total"], stages["thumbnail"]["state"]) == (3, 3, "done")
        assert stages["nlp-draft"]["state"] == "running" and stages["nlp-draft"]["in_flight"] == ["letter-000.jpg"]
        assert stages["embed"]["state"] == "waiting" and stages["embed"]["in_flight"] == []
    finally:
        derivatives._progress.pop(derivatives._key(library), None)
