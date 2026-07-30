from PIL import Image
from fastapi import HTTPException
import pytest

from fichero_server.media.image_ops import apply_operation


def test_rotate_and_straighten_use_bicubic_white_fill(monkeypatch):
    seen = []
    original = Image.Image.rotate

    def rotate(self, *args, **kwargs):
        seen.append(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "rotate", rotate)
    image = Image.new("RGB", (10, 10), "black")
    for operation in ("rotate", "straighten"):
        apply_operation(image, {"op": operation, "params": {"angle": 3}})
    assert all(item["resample"] == Image.Resampling.BICUBIC and item["fillcolor"] == "white" for item in seen)


def test_denoise_replays_deterministically():
    image = Image.new("RGB", (9, 9), "white")
    image.putpixel((4, 4), (0, 0, 0))
    operation = {"op": "denoise", "params": {"radius": 3}}
    assert apply_operation(image, operation).tobytes() == apply_operation(image, operation).tobytes()


def test_auto_deskew_reuses_straighten_rotation():
    image = Image.new("RGB", (10, 10), "white")
    assert apply_operation(image, {"op": "auto_deskew", "params": {"angle": 3}}).size != image.size


def test_auto_crop_border_removes_dark_margin():
    image = Image.new("RGB", (10, 10), "black")
    for x in range(2, 8):
        for y in range(2, 8):
            image.putpixel((x, y), (255, 255, 255))
    assert apply_operation(image, {"op": "auto_crop_border", "params": {}}).size == (6, 6)


def test_crop_missing_dimensions_raises_instead_of_using_full_image():
    image = Image.new("RGB", (10, 10), "white")

    with pytest.raises(HTTPException, match="missing required params"):
        apply_operation(image, {"op": "crop", "params": {"left": 0, "top": 0}})


def _pixels(image: Image.Image) -> list:
    """Pixel list without Pillow's deprecated getdata (#4337)."""
    width, height = image.size
    return [image.getpixel((x, y)) for y in range(height) for x in range(width)]


def test_adaptive_binarize_returns_bilevel_image():
    image = Image.new("L", (2, 1))
    image.putdata([20, 200])
    assert set(_pixels(apply_operation(image, {"op": "adaptive_binarize", "params": {}}))) == {(0, 0, 0), (255, 255, 255)}


def test_adaptive_binarize_splits_on_the_mean_not_a_fixed_midpoint():
    """The threshold is the image's own mean, so a dark page still separates.

    Every pixel here is below 128, so a hardcoded midpoint would return an
    all-black image and silently destroy the page. Also pins the behaviour
    across the switch from sum(getdata()) to ImageStat, which must compute the
    same mean rather than an approximation.
    """
    image = Image.new("L", (4, 1))
    image.putdata([10, 20, 30, 100])  # mean 40

    result = _pixels(apply_operation(image, {"op": "adaptive_binarize", "params": {}}))

    assert result == [(0, 0, 0), (0, 0, 0), (0, 0, 0), (255, 255, 255)], result


def test_adaptive_binarize_on_a_flat_image_is_all_white():
    """A uniform image has mean == its value, and the split is `>=`."""
    image = Image.new("L", (3, 2), 77)

    assert set(_pixels(apply_operation(image, {"op": "adaptive_binarize", "params": {}}))) == {(255, 255, 255)}
