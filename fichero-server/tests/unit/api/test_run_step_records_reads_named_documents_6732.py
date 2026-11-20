"""#6732: naming a run's documents reads only those documents, never the whole library."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.models import Artifact, Document


@pytest.fixture
def library():
    from fichero_server.db import Database

    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "fichero.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


def test_run_step_records_does_not_load_every_document(library, monkeypatch):
    from fichero_server.api.routes.workflow_execution import threads

    docs = [Document(name=f"page-{i}.png", path=f"/tmp/page-{i}.png") for i in range(60)]
    for doc in docs:
        library.save(doc)
    library.save(Artifact(document_id=docs[3].id, run_id="run-1", step_name="s", artifact_type="transcription", content="x"))

    loaded: list[type] = []
    real_query = library.query

    def counting_query(model, **filters):
        loaded.append(model)
        return real_query(model, **filters)

    monkeypatch.setattr(library, "query", counting_query)
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(threads, "build_run_steps", fake_build)
    run = SimpleNamespace(progress_timeline=[])
    threads._run_step_records(library, "run-1", run=run, planned_steps=[], node_name_map={})

    assert Document not in loaded  # the library's documents are not read to name a few
    assert captured["document_names"] == {docs[3].id: "page-3.png"}
