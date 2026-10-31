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


# With #6296 the finder reads the page's CURRENT image while the page box stays on the photograph. Unconverted, the box would cut
# the wrong part of an edited page and the lines would land beside the ink.

def _edited(db, page, operations):
    from fichero_server.models import ImageEditChain

    db.save(ImageEditChain(document_id=page.id, operations=operations))


def test_a_page_box_on_a_page_cropped_in_preview_cuts_the_same_paper_and_the_lines_land_on_the_photograph(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, BOX)
    _edited(db, page, [{"op": "crop", "params": {"left": 200, "top": 40, "width": 800, "height": 720}}])

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(600, 640)], "the box's own paper, measured on the edited image (800 x 720)"
    ((x, y, _w, _h),) = _lines(db, page)
    assert abs(x - (0.3 + 20 / W)) < 1e-6 and abs(y - (0.1 + 20 / H)) < 1e-6, "cut -> edited image -> photograph"
    assert abs(account["area_saved"] - (1 - 600 * 640 / (800 * 720))) < 1e-6, "the share of the image read, not of the photograph"
    assert (account["lines_inside"], account["lines_outside"]) == (1, 0)


def test_a_page_box_on_a_page_turned_in_preview_is_turned_with_it(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, BOX)
    _edited(db, page, [{"op": "rotate", "params": {"angle": 90}}])

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(640, 600)], "the same paper, a quarter turn round"
    ((x, y, w, h),) = _lines(db, page)
    assert BOX[0] <= x and x + w <= BOX[0] + BOX[2] + 1e-6 and BOX[1] <= y and y + h <= BOX[1] + BOX[3] + 1e-6
    assert (account["lines_inside"], account["lines_outside"]) == (1, 0)


def test_a_rendition_already_cut_to_the_page_is_not_cut_again(db, tmp_path, monkeypatch):
    from fichero_server.models import NodeRegion, Rendition
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, BOX)
    crop = tmp_path / "crop.png"
    Image.new("RGB", (600, 640), (200, 200, 200)).save(crop)
    db.save(Rendition(document_id=page.id, role="crop", path=str(crop), pixel_width=600, pixel_height=640,
                      transform=NodeRegion(rect=BOX)))

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(600, 640)] and "cropped" not in account, "the box is the whole rendition"
    ((x, y, _w, _h),) = _lines(db, page)
    assert abs(x - (0.3 + 20 / W)) < 1e-6 and abs(y - (0.1 + 20 / H)) < 1e-6


def test_a_box_off_the_edited_image_leaves_the_edit_whole(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub(seen))
    page = _page(db, tmp_path, [0.0, 0.0, 0.2, 0.2])
    _edited(db, page, [{"op": "crop", "params": {"left": 500, "top": 400, "width": 500, "height": 400}}])

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(500, 400)] and "cropped" not in account, "a person's edit is the last word"


def _tagged_copy(tmp_path, tag):
    """An upright 100x60 scene (blue left half, red 20x10 marker in its top-left corner) saved as the raw pixels that EXIF
    `tag` turns upright (none: as it is). Returns (path, the upright scene's marker box as fractions)."""
    from PIL import ImageOps

    scene = Image.new("RGB", (100, 60), (0, 0, 255))
    scene.paste((255, 0, 0), (0, 0, 20, 10))
    inverse = {3: Image.Transpose.ROTATE_180, 6: Image.Transpose.ROTATE_90, 8: Image.Transpose.ROTATE_270}
    raw = scene.transpose(inverse[tag]) if tag else scene
    exif = Image.Exif()
    if tag:
        exif[0x0112] = tag
    path = tmp_path / f"copy{tag}.jpg"
    raw.save(path, exif=exif, quality=100, subsampling=0)
    with Image.open(path) as saved:
        assert ImageOps.exif_transpose(saved).size == (100, 60)
    return str(path)


def test_the_page_box_cuts_the_same_paper_through_every_exif_orientation(tmp_path):
    """#6302: a copy that keeps an orientation tag had its page box dropped (the whole copy was read). Whatever the tag, the
    box around the red marker (top-left 20x10 of the upright 100x60 scene) must cut exactly 20x10 of red."""
    from fichero_server.media.current_image import PageImage
    from fichero_server.media.frame_map import exif_map, identity
    from fichero_server.recipes.regions import page_box_on, page_crop

    box = [0.0, 0.0, 0.2, 10 / 60]
    for tag in (0, 3, 6, 8):
        path = _tagged_copy(tmp_path, tag)
        with Image.open(path) as raw:
            to_image = exif_map(tag, raw.size).inverse() if tag else identity(raw.size)  # upright photograph -> file pixels
        page = PageImage(path, "rendition", path, to_image=to_image)

        carried = page_box_on(page, box)
        cut = page_crop(path, carried, str(tmp_path))

        assert cut is not None, f"tag {tag}: the box was dropped, the whole copy would be read"
        crop_path, (left, top), whole = cut
        with Image.open(crop_path) as crop:
            assert (crop.size, (left, top), whole) == ((20, 10), (0, 0), (100, 60)), f"tag {tag}"
            assert crop.getpixel((1, 1))[0] > 240 and crop.getpixel((18, 8))[0] > 240, f"tag {tag}: not the red marker"
            assert crop.getpixel((10, 5))[2] < 15, f"tag {tag}: blue leaked in"
