"""Review fixes for Prepare Images (code review 2026-10-29: Stage 1 MED 2/4/5, Stage 2 MED 4/8, and the LOWs, #5382).

Pictures are drawn here (a tilted page on a dark table, a big blank scan); no real page text.
"""
from __future__ import annotations

import tracemalloc
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fichero_server.media import find_page as module
from fichero_server.models import DocType, Document, FileType, Rendition
from tests.unit.media.test_find_page import scan
from tests.unit.media.test_square_page import H, W, photo


@pytest.mark.parametrize("angle", [6.0, 10.0])
def test_a_tilted_pages_box_takes_in_its_corners_and_a_rim(angle):
    """MED 2: the trimmed box fell 55-90 px inside a tilted page's corners, so Kraken lost the lines there."""
    image, corners = photo(angle)
    found = module.find_page_contour(image)
    assert found is not None
    x, y, w, h = found.box
    pad = 0.005  # most of the rim (1 % of the long side) must be there even after rounding
    for cx, cy in corners:
        assert x - 1e-9 <= cx - pad + 0.004 and cx + pad - 0.004 <= x + w + 1e-9, (found.box, corners)
        assert y - 1e-9 <= cy - pad + 0.004 and cy + pad - 0.004 <= y + h + 1e-9, (found.box, corners)


def test_a_big_scan_is_shrunk_before_it_becomes_rgb():
    """MED 4: a 66 MP scan was converted to RGB at full size first (+575 MB). Peak memory is a few MB now."""
    big = Image.new("L", (6000, 8000), 200)
    tracemalloc.start()
    try:
        small = module._work_copy(big)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert max(small.shape[:2]) == module.WORK_SIDE
    assert peak < 20_000_000, f"peak {peak / 1e6:.0f} MB: the full-size RGB copy is back"


def test_a_vision_outline_that_takes_in_the_mount_is_not_trusted(monkeypatch):
    """MED 5: only the 15 % minimum area gated Vision, so a wrong outline above 0.5 confidence cropped the page."""
    from fichero_server.media import page_split
    from fichero_server.media.page_split import Outline

    wrong = ((0.03, 0.03), (0.97, 0.03), (0.97, 0.97), (0.03, 0.97))  # paper, mount, ruler and card together
    monkeypatch.setattr(page_split, "detect_document_outline", lambda path: Outline((0, 0, 1, 1), 0.9, "apple-vision", wrong))
    assert module.find_page_vision(scan()) is None
    assert module.find_page(scan()).method == "contour"

    right = ((0.22, 0.24), (0.9, 0.24), (0.9, 0.9), (0.22, 0.9))  # inside the paper (330-1450 x 260-1100 of 1600x1200)
    monkeypatch.setattr(page_split, "detect_document_outline", lambda path: Outline((0, 0, 1, 1), 0.9, "apple-vision", right))
    assert module.find_page_vision(scan()).method == "vision"


def _doc(db, path: Path) -> Document:
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    return doc


def test_each_rendition_names_the_one_before_it_and_a_rerun_leaves_no_old_files(db, tmp_path, monkeypatch):
    """Stage 2 MED 8 and MED 4: squared -> flattened -> rotated -> deskewed traced back to the photograph, and the files of
    a re-run replace the old ones on disk."""
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    image, _ = photo()
    path = tmp_path / "tilted.png"
    image.save(path)
    doc = _doc(db, path)

    crop_pages(db, [doc.id], "run-1", prepare=True)
    first = {r.role: r for r in db.query(Rendition, document_id=doc.id)}
    assert {"crop", "squared"} <= set(first)
    # crop and squared are both made from the photograph itself; each later step names the rendition before it
    assert first["crop"].derived_from_rendition_id is None and first["squared"].derived_from_rendition_id is None
    ids = {r.id: r.role for r in first.values()}
    chained = [r for r in first.values() if r.role not in ("crop", "squared")]
    assert all(ids[r.derived_from_rendition_id] in ("crop", "squared", "flattened", "rotated") for r in chained)
    assert all(r.transform.rendition_id == r.derived_from_rendition_id for r in chained)
    old_files = {Path(r.path) for r in first.values()}
    assert all(f.exists() for f in old_files)

    crop_pages(db, [doc.id], "run-2", prepare=True)
    second = db.query(Rendition, document_id=doc.id)
    assert {r.role for r in second} == set(first), "no role is lost or doubled"
    assert len(second) == len(first)
    assert not any(f.exists() for f in old_files), "the first run's files are gone from disk"
    assert all(Path(r.path).exists() for r in second)


def test_a_page_that_stops_being_found_loses_its_stale_renditions(db, tmp_path, monkeypatch):
    """Stage 2 MED 8: a role not rewritten on a re-run kept its stale rendition."""
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    image, _ = photo()
    path = tmp_path / "tilted.png"
    image.save(path)
    doc = _doc(db, path)
    crop_pages(db, [doc.id], "run-1", prepare=True)
    assert db.query(Rendition, document_id=doc.id)

    full = Image.new("RGB", (W, H), (225, 212, 180))  # now the page fills the frame, with writing: no page to cut
    for y in range(100, 800, 60):
        for x in range(100, 1100, 70):
            full.paste((30, 30, 40), (x, y, x + 40, y + 12))
    full.save(path)
    crop_pages(db, [doc.id], "run-2", prepare=True)
    assert not db.query(Rendition, document_id=doc.id)


def test_an_iphone_mpo_photograph_stays_a_jpeg_and_no_half_written_file_is_left(db, tmp_path):
    from fichero_server.recipes.prepare import prepare_pages

    faded = Image.new("RGB", (200, 260), (170, 165, 150))
    faded.paste((120, 118, 110), (30, 40, 150, 60))
    path = tmp_path / "phone.jpg"
    faded.save(path, format="MPO", save_all=True, append_images=[faded])
    assert Image.open(path).format == "MPO"
    doc = _doc(db, path)

    account = prepare_pages(db, [doc.id], "run-1")

    (row,) = db.query(Rendition, document_id=doc.id)
    assert account["prepared"] == 1 and row.path.endswith(".jpg")
    assert not list((Path(db.path).parent / "files").rglob("*.part"))


def test_a_zero_tile_does_not_crash_the_contrast_step():
    from fichero_server.media.image_ops import apply_clahe_contrast

    out = apply_clahe_contrast(Image.fromarray(np.full((40, 40, 3), 120, np.uint8)), tile=0)
    assert out.size == (40, 40)


def test_16_bit_and_tiny_images_are_not_turned_white_by_the_contrast_step():
    import warnings

    from fichero_server.media.image_ops import apply_clahe_contrast

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        deep = Image.fromarray(np.random.default_rng(0).integers(0, 40000, (60, 60)).astype("uint16"))
    assert np.asarray(apply_clahe_contrast(deep)).mean() < 200
    assert np.asarray(apply_clahe_contrast(Image.fromarray(np.full((4, 4, 3), 120, np.uint8)))).mean() < 200
