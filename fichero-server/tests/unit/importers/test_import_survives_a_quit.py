"""Each saved batch of a folder import has its thumbnail jobs, so a quit leaves no page without one (#6829, #739).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.resume.jobs-are-queued-with-each-batch`. Driven through `import_folder_impl` (the body of
`POST /api/ingest/folder`), on the real jobs table.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.api.routes.ingest.core import IngestFolderRequest, import_folder_impl
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document

FILES = 230  # more than two batches of `_INGEST_BATCH_SIZE` (100)


@pytest.fixture
def lib(db, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    monkeypatch.setattr(derivatives, "_emit_queue_activity", lambda *a, **k: None)
    jobs.set_paused(True)  # nothing runs: the rows stay where the test puts them
    folder = tmp_path / "Box 3"
    folder.mkdir()
    for i in range(FILES):
        (folder / f"img{i:04d}.png").write_bytes(b"png-%d" % i)
    yield db, folder, Path(db.path).parent
    jobs.set_paused(False)


def _request(folder):
    return IngestFolderRequest(path=str(folder), mode="link", extract_text=False)


def _thumbnail_subjects(db):
    return {r[0] for r in db.execute_fetchall("SELECT subject FROM jobs WHERE kind = 'thumbnail'")}


def test_each_saved_batch_has_its_jobs_before_the_import_ends(lib):
    db, folder, library = lib
    seen = {"files": 0}

    def on_progress(current, total, fetching=0.0):
        seen["files"] = current

    # The import is cut off after the third batch's files would be next: no end-of-import queueing happens.
    with pytest.raises(RuntimeError, match="killed"):
        def kill():
            if seen["files"] >= 200:
                raise RuntimeError("killed")
            return False

        import_folder_impl(db, _request(folder), library, on_progress=on_progress, should_cancel=kill)

    saved = {d.id for d in db.query(Document) if d.path and d.doc_type != DocType.folder}
    assert len(saved) >= 200
    assert saved <= _thumbnail_subjects(db), "a saved page has no thumbnail job"
