"""Find Regions runs inside the page region (`prep.page.detected-before-lines`, `prep.page.kraken-time-saved-is-reported`,
#6189): Kraken is given only the page's crop, and every region and line comes back in the whole image's frame.

WHY: on a scan with a ruler and a dark border Kraken read the ruler's numerals as lines and spent its time on the empty
mount. Kraken is stubbed at its one seam (`segment_lines`): it answers in the frame of whatever image it is given, and
sees a ruler line only when the ruler is in that image.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document, FileType

W, H = 1000, 800
REGIONS = {"id": "regions", "job": "find-regions", "model": {"kraken": "blla", "kraken_version": "bundled"}}
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

    monkeypatch.setattr(yolo_runtime, "is_installed", lambda model_id: True)  # the weights are here; the finder is stubbed
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


def _tagged(tmp_path, tag, upright_size, name):
    """A picture whose upright size is `upright_size`, saved as the raw pixels that EXIF `tag` turns upright (1: no tag)."""
    w, h = upright_size
    raw = (h, w) if tag in (5, 6, 7, 8) else (w, h)
    exif = Image.Exif()
    if tag != 1:
        exif[0x0112] = tag
    path = tmp_path / f"{name}{tag}.jpg"
    Image.new("RGB", raw, (90, 90, 90)).save(path, exif=exif)
    return path


def _upright_stub(seen):
    """Kraken's seam as it is in life: it reads the UPRIGHT picture, and answers with one line 20 px in from its edges."""
    def segment(path, **_):
        from fichero_server.media.upright import upright_size
        with Image.open(path) as image:
            w, h = upright_size(image)
        seen.append((w, h))
        return {"width": w, "height": h, "regions": [], "lines": [
            {"id": "text", "regions": [], "polygon": [[20, 20], [w - 20, 20], [w - 20, 60], [20, 60]], "baseline": [[20, 55], [w - 20, 55]]}]}
    return segment


def _copy_and_find(db, tmp_path, monkeypatch, tag, box, cut):
    """The 1000x800 (upright) photograph, tagged like its copy, with `box` as its page box, and a tagged copy of it: half size (`cut` None) or cut to the
    fractions `cut` of the photograph and kept at full size. Returns (Kraken saw, account, the stored line)."""
    from fichero_server.models import NodeRegion, Rendition
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _upright_stub(seen))
    photo = _tagged(tmp_path, tag, (W, H), "photo")  # a phone photograph: its copies keep its tag
    page = Document(name=photo.name, doc_type=DocType.file, file_type=FileType.image, path=str(photo),
                    metadata={"page_box": box} if box else {})
    db.save(page)
    if cut:
        size = (round(cut[2] * W), round(cut[3] * H))
        copy = _tagged(tmp_path, tag, size, "cut")
        with Image.open(copy) as opened:  # as an importer records it: the file's own (raw) size
            raw = opened.size
        db.save(Rendition(document_id=page.id, role="crop", path=str(copy), pixel_width=raw[0], pixel_height=raw[1],
                          transform=NodeRegion(rect=cut)))
    else:
        copy = _tagged(tmp_path, tag, (W // 2, H // 2), "half")
        db.save(Rendition(document_id=page.id, role="enhanced", path=str(copy), pixel_width=W // 2, pixel_height=H // 2))
    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")
    lines = _lines(db, page)
    assert len(lines) == 1, f"tag {tag}: {lines}"
    return seen, account, lines[0]


def _near(got, want, tag):
    assert all(abs(a - b) < 0.003 for a, b in zip(got, want, strict=True)), f"tag {tag}: {[round(v, 4) for v in got]} != {want}"


def test_a_half_size_tagged_copy_is_cut_to_the_page_and_its_lines_land_on_the_photograph(db, tmp_path, monkeypatch):
    """#6302, hand-worked: BOX is x 300-900, y 80-720 of the 1000x800 photograph = 150-450, 40-360 of the 500x400 copy, so
    Kraken sees 300x320; its line (20..280, 20..60) is 170..430, 60..100 of the copy = [.34, .15, .52, .1] of the photograph."""
    for tag in range(1, 9):
        sub = tmp_path / f"t{tag}"
        sub.mkdir()
        seen, account, line = _copy_and_find(db, sub, monkeypatch, tag, BOX, None)
        assert seen == [(300, 320)], f"tag {tag}: Kraken saw {seen}"
        _near(line, [0.34, 0.15, 0.52, 0.1], tag)
        assert (account["lines_inside"], account["lines_outside"]) == (1, 0), f"tag {tag}"


def test_a_tagged_copy_with_no_page_box_puts_its_lines_on_the_photograph(db, tmp_path, monkeypatch):
    """No box: Kraken reads the whole 500x400 upright copy; its line is 20..480, 20..60 = [.04, .05, .92, .1]."""
    for tag in range(1, 9):
        sub = tmp_path / f"t{tag}"
        sub.mkdir()
        seen, _, line = _copy_and_find(db, sub, monkeypatch, tag, None, None)
        assert seen == [(500, 400)], f"tag {tag}: Kraken saw {seen}"
        _near(line, [0.04, 0.05, 0.92, 0.1], tag)


def test_a_tagged_copy_cut_from_the_photograph_carries_an_off_centre_box_and_its_lines(db, tmp_path, monkeypatch):
    """The copy is the photograph's x 200-1000, y 40-760 (rect [.2, .05, .8, .9], 800x720). BOX is x 100-700, y 40-680 of it,
    so Kraken sees 600x640; its line (20..580, 20..60) is 120..680, 60..100 of the copy = 320..880, 100..140 of the
    photograph = [.32, .125, .56, .05]."""
    for tag in range(1, 9):
        sub = tmp_path / f"t{tag}"
        sub.mkdir()
        seen, account, line = _copy_and_find(db, sub, monkeypatch, tag, BOX, [0.2, 0.05, 0.8, 0.9])
        assert seen == [(600, 640)], f"tag {tag}: Kraken saw {seen}"
        _near(line, [0.32, 0.125, 0.56, 0.05], tag)
        assert (account["lines_inside"], account["lines_outside"]) == (1, 0), f"tag {tag}"


def _bad_rendition_page(db, tmp_path, case):
    """A page with one rendition that cannot be read, four ways (each opens a file the old code opened unguarded)."""
    from fichero_server.models import NodeRegion, Rendition

    page = _page(db, tmp_path, BOX)
    ok = tmp_path / "ok.png"
    Image.new("RGB", (800, 640)).save(ok)
    notpic = tmp_path / "notpic.png"
    notpic.write_text("not a picture")
    gone = str(tmp_path / "gone.png")
    cut = NodeRegion(rect=[0.1, 0.1, 0.8, 0.8])
    if case == "no transform, not a picture":
        db.save(Rendition(document_id=page.id, role="enhanced", path=str(notpic), pixel_width=1000, pixel_height=800))
    elif case == "transform, no size, not a picture":
        db.save(Rendition(document_id=page.id, role="crop", path=str(notpic), transform=cut))
    else:  # a turn of a parent whose file is gone: the parent has no transform, or a transform and no recorded size
        parent = Rendition(document_id=page.id, role="enhanced" if case.startswith("parent with no") else "crop", path=gone,
                           **({"transform": cut} if "with transform" in case else {}),
                           **({"pixel_width": 1000, "pixel_height": 800} if "no transform" in case else {}))
        db.save(parent)
        db.save(Rendition(document_id=page.id, role="rotated", path=str(ok), pixel_width=800, pixel_height=640,
                          derived_from_rendition_id=parent.id,
                          transform=NodeRegion(rect=[0, 0, 1, 1], rendition_id=parent.id, angle=90)))
    return page


BAD_RENDITIONS = ("no transform, not a picture", "transform, no size, not a picture", "parent with no transform, file missing",
                  "parent with transform, no recorded size, file missing")


def test_a_rendition_that_cannot_be_read_does_not_stop_the_batch(db, tmp_path, monkeypatch):
    """Each bad rendition is passed over (the photograph is read) and the other page in the batch is still found; the same
    goes for the two other callers of the page's current image (tie_text's `_current_image`, line_check's inline call)."""
    from fichero_server.checking.tie_text import _current_image
    from fichero_server.media.current_image import current_page_image
    from fichero_server.recipes.regions import find_regions

    for case in BAD_RENDITIONS:
        sub = tmp_path / str(BAD_RENDITIONS.index(case))
        sub.mkdir()
        seen: list = []
        monkeypatch.setattr(kraken_runtime, "segment_lines", _upright_stub(seen))
        bad = _bad_rendition_page(db, sub, case)
        good = _page(db, sub, BOX)

        account = find_regions(db, [bad.id, good.id], "run-1", "blla", provider="kraken")

        assert account["pages"] == 2 and seen == [(600, 640), (600, 640)], f"{case}: {account} {seen}"
        assert account["renditions_passed_over"] == 1, f"{case}: the pass-over is counted: {account}"
        for current in (_current_image(db, bad), (current_page_image(db, bad, library_root=sub)).for_geometry()):
            assert current.is_original and "could not be read or followed" in current.why, f"{case}: {current.why}"


def test_a_turn_of_a_tagged_cut_copy_follows_the_copys_upright_picture(db, tmp_path):
    """The photograph's point (300, 100) is (100, 60) in the copy cut at rect [.2, .05, .8, .9] (800x720 upright); a quarter turn
    counter-clockwise (x, y) -> (y, 800 - x) of that is (60, 700) in the 720x800 turned picture, whatever tag the files keep."""
    from fichero_server.media.current_image import current_page_image
    from fichero_server.models import NodeRegion, Rendition

    for tag in range(1, 9):
        sub = tmp_path / f"t{tag}"
        sub.mkdir()
        photo = _tagged(sub, tag, (W, H), "photo")
        page = Document(name=photo.name, doc_type=DocType.file, file_type=FileType.image, path=str(photo))
        db.save(page)
        cut = _tagged(sub, tag, (800, 720), "cut")
        with Image.open(cut) as opened:
            raw = opened.size
        parent = Rendition(document_id=page.id, role="crop", path=str(cut), pixel_width=raw[0], pixel_height=raw[1],
                           transform=NodeRegion(rect=[0.2, 0.05, 0.8, 0.9]))
        db.save(parent)
        turned = sub / "turned.png"
        Image.new("RGB", (720, 800)).save(turned)
        db.save(Rendition(document_id=page.id, role="rotated", path=str(turned), pixel_width=720, pixel_height=800,
                          derived_from_rendition_id=parent.id,
                          transform=NodeRegion(rect=[0, 0, 1, 1], rendition_id=parent.id, angle=90)))

        image = current_page_image(db, page, library_root=sub)

        assert image.kind != "original" and Path(image.path) == turned, f"tag {tag}: {image.why}"
        x, y = image.to_image.pixels(300, 100)
        assert (round(x), round(y)) == (60, 700), f"tag {tag}: {(x, y)}"


#: The upright picture's pixels (x, y) to the raw file's, per EXIF tag, worked by hand from the tag's meaning (W, H: the
#: upright size), NOT taken from `exif_map`: (a, b, c, d, e, f) with x' = a x + b y + c, y' = d x + e y + f.
def _raw_of_upright(tag, w, h):
    return {1: (1, 0, 0, 0, 1, 0), 2: (-1, 0, w, 0, 1, 0), 3: (-1, 0, w, 0, -1, h), 4: (1, 0, 0, 0, -1, h),
            5: (0, 1, 0, 1, 0, 0), 6: (0, 1, 0, -1, 0, w), 7: (0, -1, h, -1, 0, w), 8: (0, -1, h, 1, 0, 0)}[tag]


def test_the_page_crop_of_a_tagged_copy_holds_the_right_pixels_for_every_tag(tmp_path):
    """A 100x60 upright page of four colours (red top-left, green top-right, blue bottom-left, yellow bottom-right, split at
    x 50, y 30) is saved as the raw pixels each EXIF tag turns upright. The off-centre box x 40-90, y 15-45 must cut a 50x30
    picture whose four corners are the four colours, whatever the tag."""
    from fichero_server.media.current_image import PageImage
    from fichero_server.media.frame_map import FrameMap, _affine
    from fichero_server.recipes.regions import page_box_on, page_crop

    scene = Image.new("RGB", (100, 60), (255, 255, 0))
    scene.paste((255, 0, 0), (0, 0, 50, 30))
    scene.paste((0, 255, 0), (50, 0, 100, 30))
    scene.paste((0, 0, 255), (0, 30, 50, 60))
    for tag in range(1, 9):
        raw = Image.new("RGB", (60, 100) if tag in (5, 6, 7, 8) else (100, 60))
        a, b, c, d, e, f = _raw_of_upright(tag, 100, 60)
        for x in range(100):  # each upright pixel to its place in the raw file
            for y in range(60):
                raw.putpixel((round(a * x + b * y + c - (a + b < 0)), round(d * x + e * y + f - (d + e < 0))), scene.getpixel((x, y)))
        exif = Image.Exif()
        exif[0x0112] = tag
        path = tmp_path / f"four{tag}.png"
        raw.save(path, exif=exif)
        to_image = FrameMap((100, 60), raw.size, _affine(a, b, c, d, e, f))
        page = PageImage(str(path), "rendition", str(path), to_image=to_image)

        box = page_box_on(page, [0.4, 0.25, 0.5, 0.5])
        cut = page_crop(str(path), box, str(tmp_path))

        assert cut is not None and cut[1] == (40, 15), f"tag {tag}: {cut}"
        with Image.open(cut[0]) as crop:
            got = [crop.getpixel(p) for p in ((4, 4), (45, 4), (4, 25), (45, 25))]
            assert crop.size == (50, 30) and got == [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)], f"tag {tag}: {got}"


def test_a_passed_over_rendition_is_warned_about_and_a_page_with_none_is_not_counted(db, tmp_path, monkeypatch, caplog):
    from fichero_server.recipes.regions import find_regions

    monkeypatch.setattr(kraken_runtime, "segment_lines", _upright_stub([]))
    caplog.set_level("WARNING")
    bad = _bad_rendition_page(db, tmp_path, "no transform, not a picture")

    find_regions(db, [bad.id], "run-1", "blla", provider="kraken")

    assert any("passed over" in r.message and r.levelname == "WARNING" for r in caplog.records)
    clean = _page(db, tmp_path, BOX)
    assert "renditions_passed_over" not in find_regions(db, [clean.id], "run-2", "blla", provider="kraken")


def test_a_good_turned_rendition_with_a_missing_parent_file_is_not_guessed_and_its_readings_stop_counting(db, tmp_path):
    """The turn's map needs its parent's frame; with the parent's file gone the page reads the photograph (no guess of 'no tag':
    a wrong guess stores wrong positions silently). Its signature is then `original`, not the turn's file name, so
    `working_lines.unread_by` (a reading counts only when read from the current image's signature) reads the page again."""
    from fichero_server.media.current_image import ORIGINAL, current_page_image

    page = _bad_rendition_page(db, tmp_path, "parent with no transform, file missing")

    current = current_page_image(db, page, library_root=tmp_path)

    assert current.is_original and current.signature == ORIGINAL != "ok.png" and current.passed_over == 1


def test_a_chain_of_turns_opens_each_file_a_bounded_number_of_times(db, tmp_path, monkeypatch):
    """`parent()` was called twice per turn, so the opens grew 5, 11, 23, 47 along a chain of turns. Three turns open 9 (21 before the fix)."""
    from fichero_server.media.current_image import current_page_image
    from fichero_server.models import NodeRegion, Rendition

    page = _page(db, tmp_path, None)
    before, size = None, (800, 640)
    for n in range(3):
        path = tmp_path / f"turn{n}.png"
        Image.new("RGB", size).save(path)
        row = Rendition(document_id=page.id, role="rotated", path=str(path), pixel_width=size[0], pixel_height=size[1],
                        derived_from_rendition_id=before.id if before else None,
                        transform=NodeRegion(rect=[0, 0, 1, 1], rendition_id=before.id if before else None, angle=90))
        db.save(row)
        before, size = row, (size[1], size[0])
    opened = []
    real = Image.open
    monkeypatch.setattr(Image, "open", lambda *a, **k: (opened.append(a[0]), real(*a, **k))[1])

    image = current_page_image(db, page, library_root=tmp_path)

    assert image.kind == "rendition" and len(opened) <= 12, f"{len(opened)} opens"


def _stub_whole_and_cut(seen):
    """Kraken's seam when the whole frame is also read: the whole frame has a text line on the paper and the ruler's line in the
    ruler strip; the page's crop has the text line only."""
    def segment(path, **_):
        with Image.open(path) as image:
            w, h = image.size
        seen.append((w, h))
        if w == W:
            lines = [{"id": "text", "regions": [], "polygon": [[350, 150], [850, 150], [850, 190], [350, 190]], "baseline": [[350, 185], [850, 185]]},
                     {"id": "ruler", "regions": [], "polygon": [[30, 0], [90, 0], [90, h], [30, h]], "baseline": [[60, 0], [60, h]]}]
        else:
            lines = [{"id": "text", "regions": [], "polygon": [[50, 50], [550, 50], [550, 90], [50, 90]], "baseline": [[50, 85], [550, 85]]}]
        return {"width": w, "height": h, "regions": [], "lines": lines}
    return segment


def test_the_run_reports_seconds_per_page_and_lines_inside_and_outside_the_page_before_and_after_when_asked(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub_whole_and_cut(seen))
    page = _page(db, tmp_path, BOX)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken", measure_whole=True)

    assert sorted(seen) == [(600, 640), (W, H)], "the whole frame was read once to measure, and the page's crop once"
    assert (account["whole_lines_inside"], account["whole_lines_outside"]) == (1, 1), account
    assert (account["lines_inside"], account["lines_outside"]) == (1, 0), account
    assert account["cropped"] == 1 and account["seconds_per_page"] == account["seconds"]
    assert account["whole_seconds_per_page"] == account["whole_seconds"] and account["whole_seconds"] > 0
    ((x, y, w, h),) = _lines(db, page)
    assert BOX[0] <= x and x + w <= BOX[0] + BOX[2] + 1e-6, "what is saved is the page's lines, not the measuring read's"


def test_without_the_ask_the_whole_frame_is_not_read_and_no_before_figures_are_reported(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub_whole_and_cut(seen))
    page = _page(db, tmp_path, BOX)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert seen == [(600, 640)] and not [k for k in account if k.startswith("whole_")]
    assert account["seconds_per_page"] == account["seconds"] and account["lines_outside"] == 0


def _stub_ruler_card_and_border(seen):
    """The whole frame holds a ruler strip down the left, a colour-card band along the top and a dark border; the page's crop holds
    only the page's own line (`image.enhance.furniture-lines-never-found`, #6189)."""
    def segment(path, **_):
        with Image.open(path) as image:
            w, h = image.size
        seen.append((w, h))
        # the page's own line: in the whole frame it sits on the paper (inside the box), in the crop at the crop's top left
        text = ([[320, 100], [880, 100], [880, 140], [320, 140]] if w == W else [[20, 20], [w - 20, 20], [w - 20, 60], [20, 60]])
        lines = [{"id": "text", "regions": [], "polygon": text, "baseline": [text[0], text[1]]}]
        if w == W:
            lines += [{"id": "ruler", "regions": [], "polygon": [[30, 0], [90, 0], [90, h], [30, h]], "baseline": [[60, 0], [60, h]]},
                      {"id": "card", "regions": [], "polygon": [[300, 5], [900, 5], [900, 70], [300, 70]], "baseline": [[300, 40], [900, 40]]},
                      {"id": "border", "regions": [], "polygon": [[0, 0], [W, 0], [W, 4], [0, 4]], "baseline": [[0, 2], [W, 2]]}]
        return {"width": w, "height": h, "regions": [], "lines": lines}
    return segment


def test_the_ruler_the_card_and_the_border_yield_no_line_inside_the_page_box_and_the_saving_is_counted(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub_ruler_card_and_border(seen))
    page = _page(db, tmp_path, BOX)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken", measure_whole=True)

    lines = _lines(db, page)
    assert len(lines) == 1 and all(BOX[0] <= x and x + w <= BOX[0] + BOX[2] + 1e-6 and BOX[1] <= y and y + h <= BOX[1] + BOX[3] + 1e-6
                                   for x, y, w, h in lines), "every line found lies inside the page box"
    assert (account["lines_inside"], account["lines_outside"]) == (1, 0)
    assert (account["whole_lines_inside"], account["whole_lines_outside"]) == (1, 3), "the box saved the ruler, the card and the border"


def test_the_same_frame_with_no_page_box_yields_the_ruler_the_card_and_the_border(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions

    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub_ruler_card_and_border([]))
    page = _page(db, tmp_path, None)

    find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert len(_lines(db, page)) == 4


def test_a_run_measures_the_saving_on_the_sample_pages_only_and_says_it_in_words(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import SAMPLE_PAGES, find_regions, saved_by_the_page_box

    seen: list = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", _stub_ruler_card_and_border(seen))
    pages = [_page(db, tmp_path / f"p{i}", BOX) if (tmp_path / f"p{i}").mkdir() is None else None for i in range(SAMPLE_PAGES + 2)]

    account = find_regions(db, [p.id for p in pages], "run-1", "blla", provider="kraken", measure_pages=SAMPLE_PAGES)

    assert seen.count((W, H)) == SAMPLE_PAGES, "the whole frame was read on the sample pages only"
    assert account["cropped"] == SAMPLE_PAGES + 2 and account["whole_lines_outside"] == 3 * SAMPLE_PAGES
    said = saved_by_the_page_box(account)
    assert said is not None and said.startswith("2 lines and ") and said.endswith(" seconds per page saved by the page box"), said


def test_a_run_that_measured_nothing_says_nothing():
    from fichero_server.recipes.regions import saved_by_the_page_box

    assert saved_by_the_page_box({"cropped": 3, "seconds": 1.0}) is None


def test_a_ruler_or_a_card_beside_the_page_has_the_regions_step_measure(mac):  # noqa: F811 -- fixture
    from fichero_server.recipes.start import plan_start
    for beside, measured in (("ruler", True), ("colour-card", True), ("nothing", False), ("dark-mount", False)):
        recipe = {"fichero_recipe": 1, "id": "t/regions", "version": "0.1.0", "title": "t", "steps": [REGIONS]}
        plan = plan_start(recipe, stays_local=True, job_answers={"beside_the_page": beside})
        regions = [run for run in plan["runs"] if run.get("job") == "find-regions"]
        assert len(regions) == 1, (beside, plan["runs"], plan["skipped"])
        assert bool(regions[0].get("measure_whole")) is measured, beside
