"""The tie and the line check read the page's CURRENT image (#6296): the person's edits applied, lines carried onto it.

Kraken is faked at its seams; each fake records the picture it was handed and where the lines were on it. The page is
274 x 396 (the shared fixture); the edit crops to 200 x 300 from (20, 40), so a step that read the photograph is seen at once.
"""
# ruff: noqa: F811 -- fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from PIL import Image

from fichero_server.llm import kraken_runtime
from fichero_server.models import Artifact, Document, DocType, ImageEditChain, Segment
from fichero_server.models.segments import SegmentPass
from tests.unit.check.test_line_against_page import _run as _run_check, folder  # noqa: F401  (fixture)
from tests.unit.check.test_tie_text_to_lines import _run as _run_tie
from tests.unit.training.test_kraken_training_set import TEACHER, _page

CROP = {"left": 20, "top": 40, "width": 200, "height": 300}
EDITS = [{"op": "crop", "page": 1, "params": CROP}]


def _edit(db, doc, operations):
    for row in db.query(ImageEditChain, document_id=doc.id):
        db.delete(row)
    if operations:
        db.save(ImageEditChain(document_id=doc.id, operations=operations))


def _recording_reader(monkeypatch, db):
    """Kraken's reader: every line reads as the text it carries; records the picture's size and each line's polygon."""
    seen = {"sizes": [], "polygons": []}

    def read(image_path, model_path, lines, **kw):
        with Image.open(image_path) as image:
            seen["sizes"].append(image.size)
        seen["polygons"].append([ln["polygon"] for ln in lines])
        return [ln.get("text") or "x" for ln in lines]

    monkeypatch.setattr(kraken_runtime, "read_given_lines", read)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    return seen


def test_the_check_reads_the_edited_page_with_its_lines_carried_onto_it(client, db, folder, monkeypatch):
    (doc,) = [d for d in db.query(Document) if d.doc_type == DocType.file]
    seen = _recording_reader(monkeypatch, db)
    _edit(db, doc, [])
    _run_check(client, db, folder)
    assert seen["sizes"][-1] == (274, 396)  # no edit: the photograph
    plain = seen["polygons"][-1]

    _edit(db, doc, EDITS)
    _run_check(client, db, folder)
    assert seen["sizes"][-1] == (200, 300)  # the edited page
    carried = seen["polygons"][-1]
    # the first line's corner moved by the crop's offset: carried onto the cropped picture, not left where it was on the photograph
    assert carried[0][0][0] == plain[0][0][0] - CROP["left"] and carried[0][0][1] == plain[0][0][1] - CROP["top"]


def test_the_tie_reads_the_edited_page_with_its_lines_carried_onto_it(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    folder = Document(name="SM_NPQ_C03", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C03_001", folder, size=(274, 396))
    (made,) = db.query(SegmentPass, document_id=doc.id)
    db.save(Artifact(document_id=doc.id, artifact_type="transcription", content="uno dos\ntres cuatro", model=TEACHER, provider="openrouter"))
    seen = _recording_reader(monkeypatch, db)
    _edit(db, doc, EDITS)

    _run_tie(client, db, {"folder": folder, "kraken": made})

    assert seen["sizes"] and seen["sizes"][-1] == (200, 300)


def test_the_tie_finds_lines_on_the_edited_page_and_stores_them_on_the_photograph(client, db, tmp_path, jobs_run_by_the_test, monkeypatch):
    folder = Document(name="SM_NPQ_C04", doc_type=DocType.folder)
    db.save(folder)
    doc = _page(db, tmp_path, "SM_NPQ_C04_001", folder, read_by=None, size=(274, 396))
    db.save(Artifact(document_id=doc.id, artifact_type="transcription", content="uno dos", model=TEACHER, provider="openrouter"))
    found_on = []

    def segment(image_path, **_):
        with Image.open(image_path) as image:
            found_on.append(image.size)
        # one line across the top of the picture it was handed (at y 10..30)
        return {"width": 200, "height": 300, "regions": [],
                "lines": [{"baseline": [[10, 25], [190, 25]], "polygon": [[10, 10], [190, 10], [190, 30], [10, 30]], "region": None}]}

    monkeypatch.setattr(kraken_runtime, "segment_lines", segment)
    _recording_reader(monkeypatch, db)
    _edit(db, doc, EDITS)

    _run_tie(client, db, {"folder": folder})

    assert found_on == [(200, 300)]  # Kraken looked at the edited page
    (pass_,) = db.query(SegmentPass, document_id=doc.id)
    (line,) = [s for s in db.query(Segment, pass_id=pass_.id) if s.kind == "line"]
    # stored as fractions of the PHOTOGRAPH: the line is 40 + 10 = 50 px down a 396 px page, not 10 px
    assert abs(line.bbox_y * 396 - (CROP["top"] + 10)) < 2 and abs(line.bbox_x * 274 - (CROP["left"] + 10)) < 2
