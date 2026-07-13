from PIL import Image
from fastapi import HTTPException
import pytest

from fichero.image_ops import apply_operation


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


def test_adaptive_binarize_returns_bilevel_image():
    image = Image.new("L", (2, 1))
    image.putdata([20, 200])
    assert set(apply_operation(image, {"op": "adaptive_binarize", "params": {}}).getdata()) == {(0, 0, 0), (255, 255, 255)}
