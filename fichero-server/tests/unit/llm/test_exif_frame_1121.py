"""## 1121 (Test 14): a pass's frame is the pass's own marker first, and the YOLO region finder's boxes say they are upright."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from fichero_server.media.upright import FRAME_UPRIGHT, frame_of_lines


def _phone_photo(path):
    image = Image.new("RGB", (40, 20), (250, 250, 250))
    exif = Image.Exif()
    exif[0x0112] = 6
    image.save(path, format="JPEG", exif=exif)
    return path


def test_a_split_line_listed_first_does_not_hide_the_passes_frame(db):
    """The check and the training set read the pass's marker first: line one may be a person's split with none of its own."""
    from fichero_server.models import Artifact, DocType, Document
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import SegmentPass
    from fichero_server.media.ocr_geometry import OCRGeometryResult

    doc = Document(name="p", doc_type=DocType.file)
    db.save(doc)
    result = OCRGeometryResult(provider="kraken", model="blla", metadata={"frame": FRAME_UPRIGHT})
    artifact = Artifact(document_id=doc.id, artifact_type="kraken-lines", content="", ocr_geometry=result)
    db.save(artifact)
    row = SegmentPass(document_id=doc.id, name="lines", provenance_kind=ProvenanceKind.workflow, source_artifact_id=artifact.id)
    db.save(row)
    split_first = [SimpleNamespace(metadata={}), SimpleNamespace(metadata={"frame": FRAME_UPRIGHT})]
    assert frame_of_lines(db, row, split_first) == FRAME_UPRIGHT
    assert frame_of_lines(db, row, [SimpleNamespace(metadata={})]) == FRAME_UPRIGHT  # the pass alone is enough
    old = SegmentPass(document_id=doc.id, name="old", provenance_kind=ProvenanceKind.workflow)
    db.save(old)
    assert frame_of_lines(db, old, [SimpleNamespace(metadata={})]) is None  # no marker anywhere: the raw pixels
    assert frame_of_lines(db, old, split_first) == FRAME_UPRIGHT  # a later line that has one still counts


def test_opencv_reads_an_exif_6_file_upright(tmp_path):
    """YOLO (ultralytics) loads pictures with cv2.imread, which applies the EXIF orientation: pinned, since the region step
    marks YOLO's boxes upright on that."""
    cv2 = pytest.importorskip("cv2")
    shape = cv2.imread(str(_phone_photo(tmp_path / "p.jpg"))).shape
    assert shape[:2] == (40, 20)  # rows, columns: the upright page is 20 wide and 40 tall


def test_the_yolo_region_finder_marks_its_boxes_upright(db, tmp_path, monkeypatch):
    from fichero_server.llm import yolo_runtime
    from fichero_server.models import DocType, Document
    from fichero_server.recipes import regions
    from fichero_server.workflows.tools import vision_base

    photo = _phone_photo(tmp_path / "p.jpg")
    doc = Document(name="p", doc_type=DocType.file, path=str(photo))
    db.save(doc)
    monkeypatch.setattr(yolo_runtime, "detect_regions", lambda path, model: [yolo_runtime.Region("Text", [0.1, 0.1, 0.5, 0.2], 0.9)])
    monkeypatch.setattr(vision_base, "page_direction", lambda library, doc_id: {})
    found, count = regions._find_on(db, doc, str(photo), 20, 40, "yolo", "m", "run", str(db.path.parent), None)
    assert count == 1
    assert found.metadata["frame"] == FRAME_UPRIGHT and all(b.metadata["frame"] == FRAME_UPRIGHT for b in found.boxes)
