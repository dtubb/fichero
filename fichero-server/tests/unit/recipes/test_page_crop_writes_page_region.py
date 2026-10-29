"""Finding the page writes the `page_region` attribute beside `page_box` (`prep.page.region-attribute-and-page-box`, #6187, #6198).

WHY: Preview draws the corners and Squaring warps from them; Leave Out and Find Regions read the box. One finding, both.
"""
from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_find_page import PAGE, H, W, scan


def test_page_crop_writes_page_region_and_the_same_page_box(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)

    account = crop_pages(db, [doc.id], "run-1")

    meta = db.get(Document, doc.id).metadata
    region = meta["page_region"]
    assert account["cropped"] == 1
    assert region["box"] == meta["page_box"] and region["method"] == "contour" and region["frame"] == "upright"
    assert len(region["quad"]) == 4 and 0.8 <= region["confidence"] <= 1.0
    assert abs(region["box"][0] - PAGE[0] / W) < 0.02 and abs(region["box"][1] - PAGE[1] / H) < 0.02
