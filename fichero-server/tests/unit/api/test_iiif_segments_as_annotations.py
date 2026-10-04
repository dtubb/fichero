"""A page's lines export as IIIF annotations on its canvas (`iiif.export.segments-as-annotations`).

Spec (source/iiif.md): "segments export as annotations with selectors and text granularity, carrying
the counting reading's text, language and maker".

WHY: a manifest is how a reading leaves Fichero for Mirador, a viewer, or another archive's tools. A
manifest that paints the image but carries no lines throws the transcription away; lines placed in
the fetched image's pixels instead of the canvas's land in the wrong place on the archive's own image.
Tested through the manifest route, as a viewer reaches it.
"""
from __future__ import annotations

import pytest

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.segments import rows_from_reads, segments_from_result

pytestmark = pytest.mark.source_model

CANVAS = "https://iiif.archive.example/vol1/canvas/1"


def _remote_page_with_lines(db) -> Document:
    doc = Document(name="f. 1", doc_type=DocType.file, file_type=FileType.image, status=Status.completed,
                   language="es",
                   metadata={"by_reference": True, "iiif_id": CANVAS, "width": 4000, "height": 6000,
                             "iiif_image": "https://iiif.archive.example/img/vol1/1/full/max/0/default.jpg",
                             "iiif_service_object": {"id": "https://iiif.archive.example/img/vol1/1",
                                                     "type": "ImageService3", "profile": "level1"}})
    db.save(doc)
    block = OCRGeometryResult(provider="openrouter", model="google/gemini-3-flash-preview",
                              text="vendo un negro\nen la ciudad", boxes=[
        OCRGeometryBox(text="vendo un negro", bbox=[0.10, 0.20, 0.50, 0.04], level="line", char_start=0, char_end=14),
        OCRGeometryBox(text="en la ciudad", bbox=[0.10, 0.25, 0.40, 0.04], level="line", char_start=15, char_end=27)])
    art = Artifact(document_id=doc.id, artifact_type="transcription", provider="openrouter",
                   model="google/gemini-3-flash-preview", content=block.text, ocr_geometry=block)
    db.save(art)
    pass_row, rows = rows_from_reads(*segments_from_result(
        document_id=doc.id, artifact_id=art.id, result=block, provider=art.provider, model=art.model,
        run_id=None, created_at=art.created_at, artifact_type="transcription"))
    db.save(pass_row)
    for row in rows:
        db.save(row)
    art.geometry_superseded_by_pass_id = pass_row.id
    db.save(art)
    return doc


def test_lines_are_annotations_on_the_canvas_with_text_language_and_maker(client, db):
    doc = _remote_page_with_lines(db)
    manifest = client.get(f"/api/iiif/iiif/manifest/{doc.id}").json()
    pages = manifest["items"][0].get("annotations") or []
    assert pages, "the canvas names no annotation page for its lines"
    page = client.get(pages[0]["id"]).json()

    lines = [a for a in page["items"] if a.get("textGranularity") == "line"]
    assert [a["body"]["value"] for a in lines] == ["vendo un negro", "en la ciudad"]
    first = lines[0]
    assert first["motivation"] == "supplementing" and first["body"]["language"] == "es"
    assert first["target"] == f"{CANVAS}#xywh=400,1200,2000,240"  # canvas pixels, not the fetched image's
    assert "gemini-3-flash-preview" in first["creator"]["name"]
