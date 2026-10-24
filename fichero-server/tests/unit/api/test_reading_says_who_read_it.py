"""A reading says who read it: model, provider, the run's workflow, and the run to open.

Spec: `source.inspector.reading-says-who-read-it`.

WHY: the Inspector's Transcription rows named only "Workflow" or a bare provider, so two readings of a
line could not be told apart or traced to the run that made them. Tested through the readings route.
"""
from __future__ import annotations

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.activity_records import WorkflowRunRecord
from fichero_server.models.segments import rows_from_reads, segments_from_result
from fichero_server.core.timeutil import utc_now

pytestmark = pytest.mark.source_model

LINE = "una linea de prueba"


def _line_read_by_a_run(db):
    doc = Document(name="page.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/path/page.jpg", status=Status.completed)
    db.save(doc)
    block = OCRGeometryResult(provider="openrouter", model="google/gemini-3-flash-preview", text=LINE, boxes=[
        OCRGeometryBox(text=LINE, bbox=[0.1, 0.1, 0.6, 0.05], level="line", char_start=0, char_end=len(LINE),
                       metadata={"baseline_px": [[10, 20], [600, 20]]})])
    artifact = Artifact(document_id=doc.id, artifact_type="transcription", provider="openrouter",
                        model="google/gemini-3-flash-preview", content=LINE, ocr_geometry=block, run_id="run-1")
    db.save(artifact)
    pass_row, rows = rows_from_reads(*segments_from_result(
        document_id=doc.id, artifact_id=artifact.id, result=block, provider=artifact.provider,
        model=artifact.model, run_id="run-1", created_at=artifact.created_at, artifact_type="transcription"))
    db.save(pass_row)
    for row in rows:
        db.save(row)
    line = next(r for r in rows if r.kind == "line")
    db.save(ContentRepresentation(document_id=doc.id, segment_id=line.id, kind="transcription", content=LINE,
                                  source_anchor=line.anchor, derived_from_artifact_id=artifact.id,
                                  producer_run_id="run-1", producer_model=artifact.model))
    db.save(WorkflowRunRecord(id="run-1", workflow_id="w1", workflow_name="Read each line", started_at=utc_now()))
    return line


def test_a_stored_reading_names_its_model_provider_step_and_run(client, db):
    line = _line_read_by_a_run(db)
    items = client.get(f"/api/segments/{line.id}/readings").json()["items"]
    assert items, "the line has a reading"
    for item in items:
        assert item["producer_model"] == "google/gemini-3-flash-preview"
        assert item["producer_provider"] == "openrouter"
        assert item["producer_run_id"] == "run-1"
        assert item["producer_step"] == "Read each line"


def test_a_reading_with_no_run_says_no_step(client, db):
    line = _line_read_by_a_run(db)
    db.save(ContentRepresentation(document_id=line.document_id, segment_id=line.id, kind="transcription",
                                  content="a typed correction", source_anchor=line.anchor))
    typed = [i for i in client.get(f"/api/segments/{line.id}/readings").json()["items"]
             if i["content"] == "a typed correction"]
    assert typed[0]["producer_run_id"] is None and typed[0]["producer_step"] is None
