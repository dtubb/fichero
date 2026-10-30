"""Find Regions runs inside the page region (`prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported`,
#6189): Kraken is given only the page's crop, and every region and line comes back in the whole image's frame.

WHY: on a scan with a ruler and a dark border Kraken read the ruler's numerals as lines and spent its time on the empty
mount. Kraken is stubbed at its one seam (`segment_lines`): it answers in the frame of whatever image it is given, and
sees a ruler line only when the ruler is in that image.
"""
from __future__ import annotations

from PIL import Image

from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document, FileType

W, H = 1000, 800
BOX = [0.3, 0.1, 0.6, 0.8]  # x, y, w, h fractions: the paper, right of the ruler


def _stub(seen):
    def segment(path, **_):
        with Image.open(path) as image:
            w, h = image.size
        seen.append((w, h))
        lines = [{"id": "text", "regions": [], "polygon": [[20, 20], [w - 20, 20], [w - 20, 60], [20, 60]],
                  "baseline": [[20, 55], [w - 20, 55]]}]
        if w == W:  # the whole frame still has the ruler in it
            lines.append({"id": "ruler", "regions": [], "polygon": [[30, 0], [90, 0], [90, h], [30, h]],
                          "baseline": [[60, 0], [60, h]]})
        return {"width": w, "height": h, "regions": [], "lines": lines}
    return segment


def _page(db, tmp_path, box):
    path = tmp_path / "scan.png"
    Image.new("RGB", (W, H), (20, 20, 20)).save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   metadata={"page_box": box} if box else {})
    db.save(doc)
    return doc


def _lines(db, doc):
    from fichero_server.llm.working_lines import working_lines
    return [(r.bbox_x, r.bbox_y, r.bbox_w, r.bbox_h) for r in working_lines(db, doc.id).lines]


def test_kraken_gets_only_the_page_and_every_line_is_in_the_whole_images_frame(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, BOX)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(600, 640)], "Kraken saw the page's crop, not the whole frame"
    ((x, y, w, h),) = _lines(db, page)
    assert BOX[0] <= x and x + w <= BOX[0] + BOX[2] + 1e-6, "inside the page, in whole-image fractions"
    assert abs(x - (0.3 + 20 / W)) < 1e-6 and abs(y - (0.1 + 20 / H)) < 1e-6
    assert account["cropped"] == 1 and 0.4 < account["area_saved"] < 0.6
    # the summary's line counts: one line, inside the page, none off it (`prep.page.kraken-time-saved-is-reported`)
    assert (account["lines_inside"], account["lines_outside"]) == (1, 0) and account["seconds"] >= 0


def test_without_a_page_box_the_whole_image_is_read_as_before(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, None)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(W, H)] and account.get("cropped", 0) == 0
    assert len(_lines(db, page)) == 2  # the ruler is found as a line: what the page box saves


def test_find_regions_never_runs_the_page_finder_itself(db, tmp_path, monkeypatch):
    """Review finding: Find Regions ran the finder on every page with no box, changing every default run and repeating the
    work when unsure. Finding the page is Prepare Images' job; Find Regions only uses the box it left."""
    from fichero_server.recipes import page_crop
    from fichero_server.recipes.regions import find_regions

    def refuse(*_a, **_k):
        raise AssertionError("find_regions must not look for the page")

    monkeypatch.setattr(page_crop, "crop_pages", refuse)
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub([]))
    page = _page(db, tmp_path, None)

    assert find_regions(db, [page.id], "run-1", "blla", provider="kraken")["pages"] == 1


def test_a_yolo_region_found_in_the_crop_comes_back_in_whole_image_fractions(db, tmp_path, monkeypatch):
    """Review LOW: the YOLO crop remap had no test. A box covering the crop's left half is the page box's left half in
    whole-image fractions."""
    from fichero_server.llm import yolo_runtime
    from fichero_server.models import Segment
    from fichero_server.recipes.regions import find_regions

    seen: list = []

    def detect(path, model_id="m", **_):
        with Image.open(path) as image:
            seen.append(image.size)
        return [yolo_runtime.Region(kind_raw="Table", rect=[0.0, 0.0, 0.5, 0.5], confidence=0.9)]

    monkeypatch.setattr(yolo_runtime, "detect_regions", detect)
    page = _page(db, tmp_path, BOX)

    find_regions(db, [page.id], "run-1", "m")

    assert seen == [(600, 640)]
    (seg,) = [s for s in db.query(Segment, document_id=page.id) if s.deleted_at is None]
    x, y, w, h = seg.bbox_x, seg.bbox_y, seg.bbox_w, seg.bbox_h
    assert (round(x, 4), round(y, 4), round(w, 4), round(h, 4)) == (0.3, 0.1, 0.3, 0.4)
