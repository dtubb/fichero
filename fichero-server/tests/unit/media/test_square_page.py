"""A lopsided page is squared from its four corners (`prep.square.perspective-from-the-quad`, #5382).

The photograph is drawn here: a ruled page turned about 15 degrees on a dark table, its corners known. WHY: a page
photographed at an angle is neither flat nor square, and the reader's lines curve with it; squaring from the corners
makes the ruling horizontal again and writes nothing for a page that already is.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from fichero_server.media.image_ops import detect_deskew_angle
from fichero_server.media.square_page import quad_is_rectangular, square_page, unsquare_points

W, H = 1200, 900
PAGE_W, PAGE_H = 600, 800


def _page() -> Image.Image:
    img = Image.new("RGB", (PAGE_W, PAGE_H), (225, 212, 180))
    d = ImageDraw.Draw(img)
    for y in range(80, PAGE_H - 60, 36):
        d.line([(50, y), (PAGE_W - 50, y)], fill=(40, 40, 70), width=3)
    return img


def photo(angle=15.0):
    """The page rotated and tilted onto a dark table; returns the photo and its corners as fractions."""
    import cv2

    page = np.asarray(_page())
    src = np.float32([(0, 0), (PAGE_W, 0), (PAGE_W, PAGE_H), (0, PAGE_H)])
    c, s = np.cos(np.radians(angle)), np.sin(np.radians(angle))
    centre = np.array([W / 2, H / 2])
    dst = np.float32([centre + np.array([c * (x - PAGE_W / 2) - s * (y - PAGE_H / 2) * 0.9,
                                         s * (x - PAGE_W / 2) + c * (y - PAGE_H / 2) * 0.9]) for x, y in src])
    dst[1] += (0, -25)  # a little perspective: the top right corner is pulled up
    warped = cv2.warpPerspective(page, cv2.getPerspectiveTransform(src, dst), (W, H), borderValue=(14, 12, 10))
    return Image.fromarray(warped), [(float(x) / W, float(y) / H) for x, y in dst]


def test_a_page_at_about_15_degrees_is_squared_within_half_a_degree():
    image, quad = photo()
    assert not quad_is_rectangular(quad, image.size)
    assert abs(detect_deskew_angle(image)) > 5  # the ruling is turned in the photograph
    squared, _ = square_page(image, quad)
    assert abs(detect_deskew_angle(squared)) < 0.5
    ratio = squared.width / squared.height
    assert abs(ratio - PAGE_W / PAGE_H) < 0.06  # the page's own shape, near enough (the top side was foreshortened)


def test_the_homography_maps_squared_pixels_back_to_the_photograph():
    image, quad = photo()
    squared, homography = square_page(image, quad)
    corners = [(0, 0), (squared.width - 1, 0), (squared.width - 1, squared.height - 1), (0, squared.height - 1)]
    back = unsquare_points(homography, corners)
    for (bx, by), (qx, qy) in zip(back, quad):
        assert abs(bx - qx * W) < 1.0 and abs(by - qy * H) < 1.0


def test_a_rectangular_quad_is_left_alone():
    assert quad_is_rectangular([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], (W, H))
    assert quad_is_rectangular([(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)][:3], (W, H))  # not a quad: nothing to do
    assert not quad_is_rectangular([(0.1, 0.1), (0.9, 0.12), (0.9, 0.9), (0.1, 0.9)], (W, H))  # 1.7 degrees off
    assert not quad_is_rectangular([(0.1, 0.1), (0.9, 0.1), (0.8, 0.9), (0.1, 0.9)], (W, H))  # sides differ by over 2 %


def test_the_edit_chain_squares_and_page_crop_writes_a_squared_rendition(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.media.image_ops import apply_operation
    from fichero_server.models import DocType, Document, FileType, Rendition
    from fichero_server.recipes.page_crop import crop_pages

    image, quad = photo()
    chained = apply_operation(image, {"op": "square", "params": {"quad": quad}})
    assert abs(detect_deskew_angle(chained)) < 0.5

    monkeypatch.setattr(module, "find_page_vision", lambda im: None)
    path = tmp_path / "tilted.png"
    image.save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    crop_pages(db, [doc.id], "run-1", prepare=True)
    (row,) = [r for r in db.query(Rendition, document_id=doc.id) if r.role == "squared"]
    assert row.transform.method == "square" and len(row.transform.homography) == 3
    assert abs(detect_deskew_angle(Image.open(row.path))) < 1.0

    flat = tmp_path / "flat.png"
    Image.new("RGB", (W, H), (14, 12, 10)).save(flat)
    ImageDraw.Draw(img := Image.open(flat)).rectangle([200, 150, 1000, 750], fill=(225, 212, 180))
    img.save(flat)
    doc2 = Document(name=flat.name, doc_type=DocType.file, file_type=FileType.image, path=str(flat), metadata={})
    db.save(doc2)
    crop_pages(db, [doc2.id], "run-1", prepare=True)
    assert not [r for r in db.query(Rendition, document_id=doc2.id) if r.role == "squared"], "a flat page writes nothing"
