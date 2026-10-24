"""One upright frame (`prep.image.one-upright-frame`, Test 14): a phone photo carries its rotation as an EXIF Orientation
tag. Preview and the thumbnail show it upright, so the segmenter's geometry (and the size recorded for the page) must be
in the same frame, or the lines land turned a quarter over the page."""
from __future__ import annotations

import inspect

import pytest
from PIL import Image

from fichero_server.llm import kraken_runtime


def _photo(path, orientation):
    """A 40x20 landscape file whose tag says the person holds it as 20x40."""
    image = Image.new("RGB", (40, 20), (250, 250, 250))
    image.putpixel((0, 0), (0, 0, 0))  # a mark in the raw top-left corner
    exif = Image.Exif()
    exif[0x0112] = orientation
    image.save(path, format="JPEG", exif=exif)
    return path


@pytest.mark.parametrize("orientation", [6, 8])
def test_a_rotated_photo_is_upright_and_its_size_says_so(tmp_path, orientation):
    path = _photo(tmp_path / "p.jpg", orientation)
    with Image.open(path) as opened:
        assert kraken_runtime.upright_size(opened) == (20, 40)
        assert kraken_runtime.upright(opened).size == (20, 40)


def test_an_upright_page_is_left_alone(tmp_path):
    path = _photo(tmp_path / "p.jpg", 1)
    with Image.open(path) as opened:
        assert kraken_runtime.upright_size(opened) == (40, 20)
        assert kraken_runtime.upright(opened).size == (40, 20)


def test_the_thumbnail_and_the_segmenter_share_one_frame(tmp_path):
    from PIL import ImageOps

    path = _photo(tmp_path / "p.jpg", 6)
    with Image.open(path) as opened:
        shown = ImageOps.exif_transpose(opened)
        assert kraken_runtime.upright(opened).tobytes() == shown.convert("RGB").tobytes()


def test_every_kraken_image_open_goes_through_upright():
    source = inspect.getsource(kraken_runtime)
    assert source.count("Image.open(image_path)") == source.count("image = upright(image)") >= 3


@pytest.mark.parametrize("orientation", [1, 6])
def test_clean_up_images_never_turns_a_page(db, tmp_path, orientation):
    """A faded page keeps its frame: the prepared copy shows upright at the size the original does."""
    from PIL import ImageDraw, ImageOps

    from fichero_server.models import DocType, Document, Rendition
    from fichero_server.recipes import prepare

    path = tmp_path / "faded.jpg"
    image = Image.new("RGB", (260, 200), (215, 215, 205))
    draw = ImageDraw.Draw(image)
    for y in range(30, 180, 20):
        draw.rectangle([20, y, 240, y + 6], fill=(160, 160, 160))
    exif = Image.Exif()
    exif[0x0112] = orientation
    image.save(path, format="JPEG", exif=exif)
    doc = Document(name="faded", doc_type=DocType.file, path=str(path))
    db.save(doc)
    with Image.open(path) as original:
        shown = ImageOps.exif_transpose(original).size
    account = prepare.prepare_pages(db, [doc.id], "run")
    assert account["prepared"] == 1
    made = [r for r in db.query(Rendition, document_id=doc.id) if r.role == prepare.ROLE]
    assert (made[0].pixel_width, made[0].pixel_height) == shown
    from pathlib import Path

    with Image.open(Path(db.path).parent / made[0].path) as out:
        assert ImageOps.exif_transpose(out).size == shown
