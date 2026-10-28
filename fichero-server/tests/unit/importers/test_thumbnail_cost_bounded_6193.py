"""`recipes-run.engine.thumbnails-cheap-and-off-the-lane` (#6193): a thumbnail of a 10.7 MP TIFF costs under 2 s and never
holds a second full-resolution copy: the page is shrunk first (a JPEG decodes reduced), then turned upright, so the EXIF
turn works on the small image. A turned page still fits its box upright. (Thumbnails run on the images lane, never the
model lane: `test_lanes_released_per_project.py`.)
WHY: dogfood B12, 95 TIFFs at 60 to 120 s a page beside a Kraken fan-out on a 16 GB Mac at 65 MB free."""
from __future__ import annotations

import time

import pytest
from PIL import Image, ImageOps

from fichero_server.db import storage

BIG = (4000, 2680)  # 10.7 MP


def _page(path, orientation=1):
    img = Image.new("RGB", BIG, (230, 220, 200))
    exif = img.getexif()
    exif[0x0112] = orientation
    img.save(path, exif=exif.tobytes())
    return path


@pytest.fixture
def turned_sizes(monkeypatch):
    storage._load_pil()  # loads Pillow into the module first, so the spy is not overwritten
    sizes = []
    real = ImageOps.exif_transpose

    def spy(img, **kw):
        sizes.append(img.size)
        return real(img, **kw)

    monkeypatch.setattr(storage, "ImageOps", type("ImageOpsSpy", (), {"exif_transpose": staticmethod(spy)}))
    return sizes


@pytest.mark.parametrize("suffix", [".tif", ".jpg"])
def test_the_page_is_shrunk_before_it_is_turned(tmp_path, turned_sizes, suffix):
    storage._load_pil()
    dest = storage._generate_image(_page(tmp_path / f"p{suffix}"), tmp_path / "t.jpg", (400, 400))
    assert dest is not None
    assert turned_sizes and max(turned_sizes[0]) <= 400, f"turned at full size: {turned_sizes}"


@pytest.mark.parametrize("suffix", [".tif", ".jpg"])
def test_a_turned_page_fits_its_box_upright(tmp_path, turned_sizes, suffix):
    storage._load_pil()
    dest = storage._generate_image(_page(tmp_path / f"p{suffix}", orientation=6), tmp_path / "t.jpg", (400, 300))
    with Image.open(dest) as out:
        assert out.size[1] > out.size[0] and out.size[0] <= 400 and out.size[1] <= 300  # portrait, inside the box


@pytest.mark.timing
def test_a_ten_megapixel_tiff_thumbnails_in_under_two_seconds(tmp_path):
    storage._load_pil()
    source = _page(tmp_path / "p.tif")
    t0 = time.monotonic()
    assert storage._generate_image(source, tmp_path / "t.jpg", (400, 400)) is not None
    assert time.monotonic() - t0 < 2.0
