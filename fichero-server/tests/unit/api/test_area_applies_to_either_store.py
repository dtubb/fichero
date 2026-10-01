"""#4985, `source.seam.area-applies-to-either-store`: a page answers "what is in this rectangle"
the same way before and after its results become segment records.

WHY: `GET /api/segments/document/{id}?area=` filtered converted rows by area and returned EVERY box
of an unconverted result: the same request meant two things depending on a fact the caller cannot
see, and the master test ("conversion changes nothing you can see") could not be run with an area.
"""
from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status

TOP, MIDDLE, BOTTOM = [0.1, 0.1, 0.6, 0.05], [0.1, 0.5, 0.6, 0.05], [0.1, 0.85, 0.6, 0.05]
AREA = "0.0,0.4,1.0,0.2"   # the middle band only


def _page(db):
    doc = Document(name="folio", doc_type=DocType.file, file_type=FileType.image, path="/p/f.jpg",
                   status=Status.completed, metadata={"width": 2000, "height": 3000})
    db.save(doc)
    db.save(Artifact(document_id=doc.id, artifact_type="transcription", provider="apple_vision",
                     ocr_geometry=OCRGeometryResult(provider="apple_vision", text="top\nmiddle\nbottom", boxes=[
                         OCRGeometryBox(text="top", bbox=TOP, level="line"),
                         OCRGeometryBox(text="middle", bbox=MIDDLE, level="line"),
                         OCRGeometryBox(text="bottom", bbox=BOTTOM, level="line"),
                     ])))
    return doc


def _in_area(client, doc_id):
    response = client.get(f"/api/segments/document/{doc_id}", params={"area": AREA})
    assert response.status_code == 200, response.text
    return sorted((s["text"], tuple(s["anchor"]["rect"])) for s in response.json()["segments"])


def test_an_unconverted_page_answers_an_area_as_a_converted_one_does(db, client):
    doc = _page(db)
    before = _in_area(client, doc.id)
    assert before == [("middle", tuple(MIDDLE))], "the block branch narrows by area too"

    registry.invoke(db, "segment.convert_and_edit", {"document_id": doc.id},
                    ActionContext(actor="system", is_bootstrap=True))
    assert _in_area(client, doc.id) == before
