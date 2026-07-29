"""apply_fuzzy_clean must not crash on RGBA/LA/P images (#1534).

Remove-Background produces an RGBA image (transparent background). Running the
fuzzy-clean / autocontrast step on it previously raised
`OSError: not supported for mode RGBA` from PIL.ImageOps.autocontrast.
"""

from __future__ import annotations

from PIL import Image

from fichero_server.workflows.tools.fuzzy_clean_images import apply_fuzzy_clean


def test_fuzzy_clean_rgba_does_not_crash_and_keeps_alpha() -> None:
    img = Image.new("RGBA", (16, 16), (120, 130, 140, 255))
    img.putpixel((0, 0), (10, 20, 30, 0))  # a transparent pixel

    out = apply_fuzzy_clean(img, despeckle_radius=3, background_clean=True)

    assert out.mode == "RGBA"
    assert out.getpixel((0, 0))[3] == 0  # alpha preserved


def test_fuzzy_clean_la_and_palette_modes() -> None:
    for mode in ("LA", "P"):
        img = Image.new("RGBA", (8, 8), (90, 90, 90, 255)).convert(mode)
        # Must not raise.
        apply_fuzzy_clean(img, background_clean=True)


def test_fuzzy_clean_rgb_still_autocontrasts() -> None:
    img = Image.new("RGB", (8, 8), (100, 100, 100))
    out = apply_fuzzy_clean(img, background_clean=True)
    assert out.mode == "RGB"
