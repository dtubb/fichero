"""A page's export carries each line's reading once; a correction keeps the machine's original.

Spec: `distill.collect.teacher-reads-the-lines` (the pass's PAGE XML export, one reading per line, is a
training set) and `source.one-store` (a converted page comes back once).

WHY: a run that writes its pass also keeps its artifact, so every line came back twice -- the stored
reading and its own echo -- and Fichero's PAGE export wrote two identical TextEquivs per line into a
distillation training set (found 2026-10-03 on the Sergio notebooks). A CORRECTION is different: the
machine's original then still stands beside it as history. Tested through the export route, the
surface a training set is made from.
"""
from __future__ import annotations

import re

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.segments import rows_from_reads, segments_from_result

pytestmark = pytest.mark.source_model

LINES = ["el engaño de lo que se compra", "por la mitad mas o menos"]


def _page_with_stored_readings(db, stored: list[str]):
    doc = Document(name="SM_NPQ_C01_005.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/path/SM_NPQ_C01_005.jpg", status=Status.completed)
    db.save(doc)
    text = "\n".join(LINES)
    starts = [0, len(LINES[0]) + 1]
    block = OCRGeometryResult(provider="openrouter", model="google/gemini-3-flash-preview", text=text, boxes=[
        OCRGeometryBox(text=line, bbox=[0.1, 0.1 + 0.1 * i, 0.6, 0.05], level="line",
                       char_start=starts[i], char_end=starts[i] + len(line),
                       metadata={"baseline_px": [[10, 20 + 40 * i], [600, 20 + 40 * i]]})
        for i, line in enumerate(LINES)])
    artifact = Artifact(document_id=doc.id, artifact_type="transcription", provider="openrouter",
                        model="google/gemini-3-flash-preview", content=text, ocr_geometry=block)
    db.save(artifact)
    pass_row, rows = rows_from_reads(*segments_from_result(
        document_id=doc.id, artifact_id=artifact.id, result=block, provider=artifact.provider,
        model=artifact.model, run_id=None, created_at=artifact.created_at, artifact_type="transcription"))
    db.save(pass_row)
    for row in rows:
        db.save(row)
    lines = [r for r in rows if r.kind == "line"]
    for row, content in zip(lines, stored):
        db.save(ContentRepresentation(document_id=doc.id, segment_id=row.id, kind="transcription",
                                      content=content, source_anchor=row.anchor))
    artifact.geometry_superseded_by_pass_id = pass_row.id
    db.save(artifact)
    return doc, pass_row


def _equivs_per_line(client, doc, pass_row) -> list[list[str]]:
    r = client.get(f"/api/documents/{doc.id}/export/pagexml", params={"pass_id": pass_row.id})
    assert r.status_code == 200, r.text
    xml = r.json()["content"]
    return [re.findall(r"<Unicode>([^<]*)</Unicode>", line) for line in xml.split("<TextLine")[1:]]


def test_each_line_is_exported_with_its_reading_once(client, db):
    doc, pass_row = _page_with_stored_readings(db, LINES)
    assert _equivs_per_line(client, doc, pass_row) == [[LINES[0]], [LINES[1]]]


def test_a_corrected_line_keeps_the_machines_original_beside_the_correction(client, db):
    corrected = "por la mitad más o menos"
    doc, pass_row = _page_with_stored_readings(db, [LINES[0], corrected])
    first, second = _equivs_per_line(client, doc, pass_row)
    assert first == [LINES[0]]
    assert sorted(second) == sorted([corrected, LINES[1]])
