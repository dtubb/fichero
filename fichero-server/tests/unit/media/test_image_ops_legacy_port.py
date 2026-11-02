"""The content box is a numpy reduction and the dark-mount method keeps its answer (`prep.crop.content-bbox-is-fast`,
`prep.page.remove-background-is-the-dark-mount-method`, #6190, #6188). Fixtures are drawn, never the owner's scans."""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from fichero_server.media.image_ops import detect_content_bbox, remove_black_background_opencv


def _loop_reference(image):  # the per-pixel loop this replaced: the answer must not change
    gray = image.convert("L")
    px = gray.load()
    xs, ys = [], []
    for y in range(gray.height):
        for x in range(gray.width):
            if px[x, y] > 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, image.width, image.height
    return min(xs), min(ys), max(xs) + 1 - min(xs), max(ys) + 1 - min(ys)


def _mount(w=600, h=400):
    rng = np.random.default_rng(3)
    arr = np.full((h, w, 3), 8, "uint8")
    arr[60:340, 90:520] = np.clip(215 + rng.normal(0, 5, (280, 430, 3)), 0, 255).astype("uint8")
    return Image.fromarray(arr)


def test_content_bbox_is_fast_and_gives_the_same_answer():
    small = _mount()
    assert detect_content_bbox(small) == _loop_reference(small) == (90, 60, 430, 280)
    assert detect_content_bbox(Image.new("RGB", (50, 40), 0)) == (0, 0, 50, 40)  # nothing: the whole frame
    big = Image.fromarray(np.full((2000, 3000, 3), 8, "uint8"))
    big.paste(Image.new("RGB", (2400, 1700), (200, 200, 200)), (300, 150))
    start = time.perf_counter()
    assert detect_content_bbox(big) == (300, 150, 2400, 1700)
    assert time.perf_counter() - start < 0.2  # the spec's bound is 0.5 s; the loop took 0.52 s


def test_remove_background_still_lifts_the_page_on_a_dark_mount():
    """An existing chain row named `remove_background` re-renders the page, unchanged (the feather adds a rim)."""
    lifted = remove_black_background_opencv(_mount())
    assert lifted.size == (448, 298) and lifted.mode == "RGBA"


def _faded_page():
    rng = np.random.default_rng(5)
    arr = np.clip(np.array([200, 190, 160]) + rng.normal(0, 3, (240, 320, 3)), 0, 255).astype("uint8")
    for y in range(40, 220, 30):
        arr[y:y + 4, 30:290] = (150, 140, 120)  # faint ink
    return Image.fromarray(arr)


def test_contrast_clahe_widens_the_lightness_and_keeps_the_colour():
    """`image.enhance.contrast-clahe`: LAB CLAHE on L (handwritten: clip 2.2, tile 8, x1.1 -5); a/b untouched."""
    import cv2

    from fichero_server.media.image_ops import apply_clahe_contrast, apply_operation

    page = _faded_page()
    out = apply_clahe_contrast(page)
    before, after = (cv2.cvtColor(np.asarray(i.convert("RGB")), cv2.COLOR_RGB2LAB) for i in (page, out))
    assert after[:, :, 0].std() > 1.25 * before[:, :, 0].std(), "ink stands out more"
    assert np.abs(after[:, :, 1:].astype(int) - before[:, :, 1:]).mean() < 2, "the page stays its colour"
    # params reach it through the edit chain, and the typescript profile is a different curve
    chained = apply_operation(page, {"op": "contrast", "params": {"profile": "typescript"}})
    assert np.abs(np.asarray(chained, int) - np.asarray(out, int)).mean() > 0.5
    # an old chain row (a bare factor) is still the PIL contrast, unchanged
    old = apply_operation(page, {"op": "contrast", "params": {"factor": 1.0}})
    assert np.array_equal(np.asarray(old), np.asarray(page))


def _tinted(b_offset: int):
    """A flat paper page with ink, its LAB b channel moved by `b_offset`."""
    import cv2

    arr = np.full((200, 300, 3), 215, "uint8")
    arr[90:96, 20:280] = 40
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    lab[:, :, 2] = np.clip(lab[:, :, 2].astype(int) + b_offset, 0, 255).astype("uint8")
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def _b_mean(image) -> float:
    import cv2

    return float(cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB)[:, :, 2].mean())


def test_yellowing_subtracts_min_8_3_cast_from_b_and_leaves_a_neutral_page_alone():
    """`image.enhance.yellowing`: cast = (mean b - 128) / 30 clamped 0-1; b - min(8, 3 x cast) when cast > 0.1, a x 0.98."""
    from fichero_server.media.enhance import yellowing

    neutral = _tinted(0)
    out, account = yellowing.run(neutral, yellowing.Params())
    assert out.tobytes() == neutral.tobytes() and account["applied"] is False and account["step"] == "yellowing"
    yellow = _tinted(12)
    cast = min(1.0, max(0.0, (_b_mean(yellow) - 128) / 30))
    assert cast > 0.1
    out, account = yellowing.run(yellow, yellowing.Params())
    assert account["applied"] is True and abs(account["strength"] - min(8, 3 * cast)) < 1e-6
    assert abs((_b_mean(yellow) - _b_mean(out)) - account["strength"]) < 0.6, "b moved by the strength"
    out, account = yellowing.run(yellow, yellowing.Params(strength=2.0))  # an explicit strength is used as given
    assert account["strength"] == 2.0 and abs((_b_mean(yellow) - _b_mean(out)) - 2.0) < 0.6


def test_sharpen_is_unsharp_mask_1_5_minus_0_5_at_sigma_3_and_leaves_flat_paper_alone():
    import cv2

    from fichero_server.media.enhance import sharpen

    arr = np.full((120, 160, 3), 200, "uint8")
    arr[:, 80:] = 100  # a step edge
    image = Image.fromarray(arr)
    out, account = sharpen.run(image, sharpen.Params())
    expected = cv2.addWeighted(arr, 1.5, cv2.GaussianBlur(arr, (0, 0), 3), -0.5, 0)
    assert np.array_equal(np.asarray(out), expected) and account["step"] == "sharpen"
    assert np.asarray(out)[60, 10].tolist() == [200, 200, 200] and np.asarray(out)[60, 150].tolist() == [100, 100, 100]
    assert np.asarray(out)[60, 77, 0] > 200 and np.asarray(out)[60, 82, 0] < 100, "the edge overshoots: it is sharper"


def test_enhance_with_method_clahe_runs_contrast_then_yellowing_then_sharpen_and_a_row_without_a_method_is_the_pil_enhance():
    from fichero_server.media.enhance import contrast, sharpen, yellowing
    from fichero_server.media.image_ops import apply_operation

    page = _tinted(12)
    out = apply_operation(page, {"op": "enhance", "params": {"method": "clahe", "profile": "typescript"}})
    step1, _ = contrast.run(page, contrast.Params(profile="typescript"))
    step2, _ = yellowing.run(step1, yellowing.Params())
    step3, _ = sharpen.run(step2, sharpen.Params())
    assert out.tobytes() == step3.tobytes()
    old = apply_operation(page, {"op": "enhance", "params": {"brightness": 1.0, "contrast": 1.0, "sharpen": 1.0}})
    assert old.tobytes() == page.tobytes(), "a stored row with no method re-renders as it did"
    with __import__("pytest").raises(Exception):
        apply_operation(page, {"op": "enhance", "params": {"method": "magic"}})


def test_a_saved_clahe_enhance_row_previews_through_the_route(client, db):
    from fichero_server.models import Document, FileType

    path = db.path.parent / "files" / "tint.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    _tinted(12).save(path)
    doc = Document(name="tint.png", path=str(path), file_type=FileType.image)
    db.save(doc)
    put = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": "enhance", "params": {"method": "clahe"}}]})
    assert put.status_code == 200, put.text
    got = client.get(f"/api/images/{doc.id}/preview")
    assert got.status_code == 200, got.text[:200]
    import io

    shown = Image.open(io.BytesIO(got.content))
    assert abs(_b_mean(shown) - _b_mean(_tinted(12))) > 1, "the preview is the enhanced page, not the source"
