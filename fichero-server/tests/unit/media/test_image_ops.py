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


def _scan_on_dark_ground() -> Image.Image:
    """A 40x40 'photographed page': dark ground, light paper, one ink stroke."""
    image = Image.new("RGB", (40, 40), (15, 15, 15))
    for x in range(10, 30):
        for y in range(10, 30):
            image.putpixel((x, y), (235, 230, 220))
    for x in range(14, 26):
        image.putpixel((x, 20), (40, 35, 30))
    return image


def test_remove_scan_background_keeps_paper_and_ink_drops_ground():
    from fichero_server.media.image_ops import remove_scan_background

    cleaned = remove_scan_background(_scan_on_dark_ground(), threshold=28)

    assert cleaned.mode == "RGBA"
    assert cleaned.getpixel((0, 0))[3] == 0  # ground is gone
    assert cleaned.getpixel((12, 12))[3] == 255  # paper survives
    assert cleaned.getpixel((20, 20))[3] == 255  # ink survives


def test_remove_scan_background_preserves_enclosed_paper():
    """Paper enclosed by ink (the counter of an 'o') must stay opaque.

    The old per-pixel colour difference erased EVERY background-coloured
    pixel; the flood fill only erases what connects to the border.
    """
    from fichero_server.media.image_ops import remove_scan_background

    image = Image.new("RGB", (30, 30), (240, 240, 240))
    for x in range(8, 22):  # closed dark ring
        image.putpixel((x, 8), (0, 0, 0))
        image.putpixel((x, 21), (0, 0, 0))
    for y in range(8, 22):
        image.putpixel((8, y), (0, 0, 0))
        image.putpixel((21, y), (0, 0, 0))

    cleaned = remove_scan_background(image, threshold=28)

    assert cleaned.getpixel((0, 0))[3] == 0  # border-connected paper removed
    assert cleaned.getpixel((10, 8))[3] == 255  # the ink ring survives
    assert cleaned.getpixel((15, 15))[3] == 255  # enclosed paper survives


def test_remove_scan_background_downscaled_flood_path():
    """Images beyond the flood working size take the downscale branch."""
    from fichero_server.media.image_ops import remove_scan_background

    image = Image.new("RGB", (1200, 40), (15, 15, 15))
    for x in range(300, 900):
        for y in range(10, 30):
            image.putpixel((x, y), (235, 235, 235))

    cleaned = remove_scan_background(image, threshold=28)

    assert cleaned.getpixel((5, 5))[3] == 0
    assert cleaned.getpixel((600, 20))[3] == 255


def _speckled_uneven_page() -> Image.Image:
    """A 256x256 page with an illumination gradient, speckles and a stroke."""
    image = Image.new("RGB", (256, 256))
    for y in range(256):
        shade = 140 + int(y * 90 / 255)  # dark top, light bottom
        for x in range(256):
            image.putpixel((x, y), (shade, shade, shade))
    for x, y in ((40, 40), (200, 60), (100, 200)):  # isolated speckles
        image.putpixel((x, y), (20, 20, 20))
    for x in range(80, 176):  # a 3px-thick stroke survives a median filter
        for y in range(120, 123):
            image.putpixel((x, y), (25, 25, 25))
    return image


def test_fuzzy_clean_removes_speckles_and_keeps_strokes():
    from fichero_server.media.image_ops import apply_fuzzy_clean

    cleaned = apply_fuzzy_clean(_speckled_uneven_page(), despeckle_radius=3, background_clean=True)

    for x, y in ((40, 40), (200, 60), (100, 200)):
        assert cleaned.getpixel((x, y))[0] > 150, "speckle must despeckle to paper"
    assert cleaned.getpixel((128, 121))[0] < 128, "ink stroke must survive"


def test_fuzzy_clean_flattens_uneven_illumination():
    """The shadowed top of the page must come out as light as the bottom."""
    from fichero_server.media.image_ops import apply_fuzzy_clean

    cleaned = apply_fuzzy_clean(_speckled_uneven_page(), despeckle_radius=3, background_clean=True)

    top = cleaned.getpixel((20, 12))[0]
    bottom = cleaned.getpixel((20, 244))[0]
    assert top > 200 and bottom > 200
    assert abs(top - bottom) < 25
