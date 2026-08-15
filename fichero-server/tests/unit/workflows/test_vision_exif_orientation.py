"""Vision inputs must be EXIF-oriented like the display path (2026-08-12).

The app's display/thumbnail path applies ``ImageOps.exif_transpose``; the
vision prep paths did not. A camera scan carrying EXIF orientation was
OCR'd on its RAW pixels, so its geometry landed rotated 90° over the
displayed page — text at the top, boxes down the right edge (Marshall
Diaries bbox repro).
"""

import base64
import io

import pytest
from PIL import Image

from fichero_server.workflows.tools.vision_base import (
    _normalize_for_vision,
    file_to_data_uri,
)

# EXIF orientation 6 = rotate 90° CW to display. A 100x60 raw image
# displays (and must reach the model) as 60x100.
_ORIENTATION_TAG = 0x0112


@pytest.fixture
def rotated_jpeg(tmp_path):
    path = tmp_path / "camera_scan.jpg"
    img = Image.new("RGB", (100, 60), "white")
    exif = img.getexif()
    exif[_ORIENTATION_TAG] = 6
    img.save(path, format="JPEG", exif=exif)
    return path


def _decode_data_uri(uri: str) -> Image.Image:
    payload = uri.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(payload)))


def test_file_to_data_uri_applies_exif_orientation(rotated_jpeg):
    decoded = _decode_data_uri(file_to_data_uri(str(rotated_jpeg)))
    assert (decoded.width, decoded.height) == (60, 100)


def test_file_to_data_uri_orients_even_without_resize(rotated_jpeg):
    # max_dimension=0 used to take the raw-bytes fast path, which keeps the
    # EXIF tag providers ignore.
    decoded = _decode_data_uri(file_to_data_uri(str(rotated_jpeg), max_dimension=0))
    assert (decoded.width, decoded.height) == (60, 100)


def test_normalize_for_vision_orients_rotated_scan(rotated_jpeg):
    path, temp = _normalize_for_vision(str(rotated_jpeg))
    try:
        assert path != str(rotated_jpeg), (
            "an EXIF-rotated scan must be re-encoded, not passed through raw"
        )
        with Image.open(path) as img:
            assert (img.width, img.height) == (60, 100)
    finally:
        if temp:
            import os

            os.unlink(temp)


def test_normalize_for_vision_still_passes_through_plain_images(tmp_path):
    path = tmp_path / "plain.jpg"
    Image.new("RGB", (100, 60), "white").save(path, format="JPEG")
    used, temp = _normalize_for_vision(str(path))
    assert used == str(path)
    assert temp is None
