"""Every stored shape of an older result converts on open, or is named as not converted (#5222).

WHY: a real user's older libraries hold many results from many eras (Javier's among them), and
the conversion runs over all of them unattended. One stored form has ever existed --
`Artifact.ocr_geometry` (normalised [x, y, w, h], top-left origin, since 2026-06-26) -- but each
producer and era fills it differently: Apple Vision lines with words, VLM boxes, a PDF's own text
layer, detected regions, Kraken's pixel polygons with their frame, box sets measured on a crop
(`rendition_id`, 2026-08-23) and rows from before that field. One fixture of each, read from the
producers' code (`git log` over media/ocr_geometry.py and each writer).

If a shape stops converting, those pages stay half old; if a bad stored box crashes the run,
nothing after it converts. A box a later validator refuses is recorded against its page, by
name, and the rest go on; the `segmentation` artifact (no engine producer ever wrote it) is left
as it was and counted by the status route (`test_conversion_starts_on_open.py`).
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.maintenance import project_conversion as pc
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Segment, SegmentPass, Status
from tests.unit.maintenance.test_project_conversion_resume import _snapshot_stub, project  # noqa: F401

pytestmark = pytest.mark.source_model

KRAKEN_FRAME = {"width": 2000, "height": 3000}


def _box(text, bbox, level="line", **extra):
    return OCRGeometryBox(text=text, bbox=bbox, level=level, **extra)


def _kraken_line(i):
    y = 300 + 200 * i
    return _box(f"k{i}", [0.1, y / 3000, 0.8, 90 / 3000], source="kraken-blla", metadata={
        "polygon_px": [[200, y], [1800, y], [1800, y + 90], [200, y + 90]],
        "baseline_px": [[200, y + 70], [1800, y + 70]],
        "pixel_frame": KRAKEN_FRAME,
    })


#: (artifact_type, provider, result) -- one per producer and era.
SHAPES = {
    "apple-vision lines and words": ("transcription", "apple_vision", OCRGeometryResult(
        provider="apple_vision", text="In the year", boxes=[
            _box("In the year", [0.1, 0.1, 0.5, 0.04]),
            _box("In", [0.1, 0.1, 0.05, 0.04], level="word", char_start=0, char_end=2),
            _box("year", [0.3, 0.1, 0.1, 0.04], level="word", char_start=7, char_end=11),
        ])),
    "vlm return_boxes": ("transcription", "gemini", OCRGeometryResult(
        provider="gemini", text="Item a cow", boxes=[_box("Item a cow", [0.12, 0.2, 0.6, 0.05])])),
    "pdf text layer": ("text_geometry", "pymupdf", OCRGeometryResult(
        provider="pymupdf", text="Chapter 1", boxes=[_box("Chapter 1", [0.2, 0.05, 0.3, 0.03], level="block")])),
    "detected regions": ("regions", "apple_vision", OCRGeometryResult(
        provider="apple_vision", boxes=[_box("", [0.05, 0.05, 0.9, 0.4], level="region"),
                                        _box("", [0.05, 0.5, 0.9, 0.4], level="region")])),
    "kraken regions with pixel polygons": ("regions", "kraken", OCRGeometryResult(
        provider="kraken", boxes=[_kraken_line(i) for i in range(3)])),
    "kraken htr": ("transcription", "kraken", OCRGeometryResult(
        provider="kraken", text="k0\nk1", boxes=[_kraken_line(0), _kraken_line(1)])),
    "merged geometry": ("text_geometry", "merge_geometry", OCRGeometryResult(
        provider="merge_geometry", text="a b", boxes=[_box("a b", [0.1, 0.6, 0.4, 0.04])])),
    "aligned transcript": ("aligned_transcript", "alignment", OCRGeometryResult(
        provider="alignment", text="the edition's line", boxes=[_box("the edition's line", [0.1, 0.7, 0.7, 0.04])])),
    "measured on a crop": ("transcription", "apple_vision", OCRGeometryResult(
        provider="apple_vision", text="crop", rendition_id="rendition-crop-1",
        boxes=[_box("crop", [0.3, 0.3, 0.2, 0.05])])),
}


def _page(db, name):
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=f"/p/{name}.jpg",
                   status=Status.completed, metadata={"width": 2000, "height": 3000})
    db.save(doc)
    return doc


def test_each_shape_becomes_its_own_pass_with_a_segment_per_box(project, monkeypatch):
    pages = {}
    for label, (kind, provider, result) in SHAPES.items():
        doc = _page(project.db, label)
        project.db.save(Artifact(document_id=doc.id, artifact_type=kind, provider=provider, ocr_geometry=result))
        pages[label] = (doc.id, len(result.boxes))
    _snapshot_stub(project.path, monkeypatch)

    run = pc.convert_project(project.db, project.path)

    assert run.failures == [], run.failures
    for label, (doc_id, boxes) in pages.items():
        [artifact] = project.db.query(Artifact, document_id=doc_id)
        assert artifact.geometry_superseded_by_pass_id, label
        [pass_row] = project.db.query(SegmentPass, document_id=doc_id)
        assert pass_row.id == artifact.geometry_superseded_by_pass_id, label
        assert len(project.db.query(Segment, pass_id=pass_row.id)) == boxes, label


def test_kraken_pixel_polygons_arrive_as_page_fractions(project, monkeypatch):
    doc = _page(project.db, "kraken")
    kind, provider, result = SHAPES["kraken regions with pixel polygons"]
    project.db.save(Artifact(document_id=doc.id, artifact_type=kind, provider=provider, ocr_geometry=result))
    _snapshot_stub(project.path, monkeypatch)
    pc.convert_project(project.db, project.path)
    first = min(project.db.query(Segment, document_id=doc.id), key=lambda s: s.anchor.rect[1])
    assert first.anchor.polygon[0] == pytest.approx([200 / 2000, 300 / 3000])


def test_a_stored_box_a_later_validator_refuses_is_named_and_the_rest_convert(project, monkeypatch):
    """Before the salvage fixes of 2026-08-27 a box could be stored outside 0..1. Saved here
    without validation, as it sits in such a library."""
    good = _page(project.db, "good")
    project.db.save(Artifact(document_id=good.id, artifact_type="transcription", provider="gemini",
                             ocr_geometry=SHAPES["vlm return_boxes"][2]))
    bad = _page(project.db, "bad")
    broken = OCRGeometryResult.model_construct(
        provider="gemini", text="x", model=None, source=None, rendition_id=None, metadata={},
        boxes=[OCRGeometryBox.model_construct(
            text="x", bbox=[0.9, 0.9, 0.4, 0.4], level="line", confidence=None, char_start=None,
            char_end=None, page_index=None, provider=None, model=None, coordinate_space="normalized",
            source=None, metadata={},
        )],
    )
    project.db.save(Artifact.model_construct(
        **{**Artifact(document_id=bad.id, artifact_type="transcription", provider="gemini").model_dump(),
           "ocr_geometry": broken}
    ))
    _snapshot_stub(project.path, monkeypatch)

    run = pc.convert_project(project.db, project.path)

    assert [f.document_id for f in run.failures] == [bad.id]
    assert run.failures[0].reason
    assert project.db.query(Artifact, document_id=good.id)[0].geometry_superseded_by_pass_id
    assert not project.db.query(Segment, document_id=bad.id)
