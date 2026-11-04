"""Denoise and binarise as enhancement steps (`image.enhance.denoise`, `image.enhance.binarise`, #6185). Fixtures are drawn,
never the owner's scans. Each step is pressed through the engine function, the editor's saved-edits and preview routes and the
workflow node that writes the rendition."""
from __future__ import annotations

import asyncio
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from fichero_server.media.enhance import binarise, denoise
from fichero_server.models import Document, FileType, Rendition


def _page(noise: float = 0.0, seed: int = 3):
    """Cream paper, five ink lines 4 px thick (and a dot at each end of one), optional salt-and-pepper noise."""
    h, w = 400, 600
    arr = np.full((h, w, 3), (232, 226, 210), "uint8")
    for y in range(60, 360, 60):
        arr[y:y + 4, 40:560] = (30, 28, 26)
    arr[200:208, 20:28] = (30, 28, 26)
    if noise:
        rng = np.random.default_rng(seed)
        hit = rng.random((h, w)) < noise
        arr[hit & (rng.random((h, w)) < 0.5)] = 0
        arr[hit & ~(arr == 0).all(axis=2)] = 255
    return Image.fromarray(arr)


def _components(image: Image.Image) -> int:
    gray = np.asarray(image.convert("L"))
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return cv2.connectedComponents(ink, connectivity=8)[0] - 1


def test_one_percent_salt_and_pepper_falls_under_005_percent_and_the_ink_components_stay():
    clean = _page()
    noisy = _page(noise=0.01)
    out, account = denoise.run(noisy, denoise.Params())
    bad = (np.abs(np.asarray(out, int) - np.asarray(clean, int)).max(axis=2) > 60).mean()
    assert bad < 0.0005, bad
    assert _components(out) == _components(clean) == 6
    assert account["radius"] == 3 and account["speck"] == 5


def test_a_speck_of_the_given_size_goes_and_a_stroke_longer_than_it_stays():
    arr = np.full((200, 300, 3), 235, "uint8")
    arr[100:103, 20:280] = 20  # a stroke 3 px thick
    arr[30:34, 40:44] = 20  # a 4 px blob
    out, account = denoise.run(Image.fromarray(arr), denoise.Params(radius=3, speck=5))
    got = np.asarray(out)
    assert got[30:34, 40:44].min() > 200 and got[101, 30:270].max() < 60
    assert account["specks_removed"] == 1
    kept, account = denoise.run(Image.fromarray(arr), denoise.Params(radius=3, speck=0))
    assert np.asarray(kept)[31, 41].max() < 60 and account["specks_removed"] == 0


def test_otsu_and_adaptive_binarise_keep_the_ink_components_within_five_percent():
    page = _page(noise=0.0)
    base = _components(page)
    for method in ("otsu", "adaptive"):
        out, account = binarise.run(page, binarise.Params(method=method))
        assert set(np.unique(np.asarray(out))) <= {0, 255} and account["method"] == method
        assert abs(_components(out) - base) <= max(1, 0.05 * base)


def test_an_even_block_is_used_as_the_next_odd_one_and_the_account_says_so():
    page = _page()
    out, account = binarise.run(page, binarise.Params(block=32))
    assert account["block"] == 33 and out.tobytes() == binarise.run(page, binarise.Params(block=33))[0].tobytes()


def test_an_old_adaptive_binarize_row_still_re_renders_to_its_old_pixels():
    from fichero_server.media.image_ops import apply_operation

    image = _page()
    gray = image.convert("L")
    mean = float(np.asarray(gray).mean())
    old = gray.point(lambda v: 255 if v >= mean else 0).convert("RGB")
    assert apply_operation(image, {"op": "adaptive_binarize"}).tobytes() == old.tobytes()


def test_an_old_denoise_row_re_renders_to_its_old_pixels_and_a_new_one_removes_specks():
    from fichero_server.media.image_ops import apply_fuzzy_clean, apply_operation

    image = _page(noise=0.01)
    old = apply_fuzzy_clean(image, despeckle_radius=5, background_clean=False)
    assert apply_operation(image, {"op": "denoise", "params": {"radius": 5}}).tobytes() == old.tobytes()
    arr = np.full((100, 100, 3), 235, "uint8")
    arr[40:44, 40:44] = 20
    assert np.asarray(apply_operation(Image.fromarray(arr), {"op": "denoise", "params": {"radius": 3, "speck": 5}}))[41, 41].min() > 200


def test_without_opencv_denoise_still_runs_the_pil_median(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_cv2(name, *a, **k):
        if name == "cv2":
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_cv2)
    image = _page(noise=0.01)
    out, account = denoise.run(image, denoise.Params(radius=3, speck=5))
    from PIL import ImageFilter

    assert out.tobytes() == image.convert("RGB").filter(ImageFilter.MedianFilter(size=3)).tobytes() and account["specks_removed"] is None


def _document(db, image, name):
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    doc = Document(name=name, path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


@pytest.mark.parametrize("op, params, bad", [
    ("denoise", {"radius": 3, "speck": 5}, {"speck": 20}),
    ("binarise", {"method": "otsu"}, {"block": 7}),
])
def test_the_editor_saves_and_previews_the_step_and_refuses_a_bad_value(client, db, op, params, bad):
    image = _page(noise=0.01)
    doc = _document(db, image, f"{op}.png")
    refused = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": op, "params": bad}]})
    assert refused.status_code == 422, refused.text
    put = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": op, "params": params}]})
    assert put.status_code == 200, put.text
    got = client.get(f"/api/images/{doc.id}/preview")
    assert got.status_code == 200, got.text[:200]
    shown = Image.open(io.BytesIO(got.content)).convert("RGB")
    assert np.abs(np.asarray(shown, int) - np.asarray(image.convert("RGB"), int)).mean() > 0.5


def test_the_denoise_node_config_comes_from_the_params_model_and_forwards_the_specks_to_the_chain(monkeypatch):
    from fichero_server.workflows.registry import get_tool_def
    from fichero_server.workflows.tools import denoise_images as tool

    config = get_tool_def("denoise_images").config_schema
    assert config["speck"]["default"] == 5 and config["speck"]["maximum"] == 9 and config["radius"]["minimum"] == 3
    monkeypatch.setattr(tool, "append_image_edit_operations", lambda inputs, state, operation: [operation("d")])
    out = asyncio.run(tool.denoise_images({"radius": 3, "speck": 7}, {}, None))
    assert out["image_edit_operations"][0]["params"] == {"radius": 3, "speck": 7}


@pytest.mark.parametrize("tool, step, role, given", [
    ("binarise_images", "binarise", "binarised", {"method": "otsu"}),
])
def test_the_node_writes_its_rendition_with_the_step_settings_and_leaves_the_source(db, tool, step, role, given):
    from fichero_server.workflows.tools import enhance_step_nodes

    doc = _document(db, _page(noise=0.01), f"{tool}.png")
    before = open(doc.path, "rb").read()
    state = {"library_path": str(db.path.parent), "run_id": "run-1", "batch_id": "batch-1"}
    out = asyncio.run(getattr(enhance_step_nodes, tool)(
        {"files": [doc.path], "documents": [{"id": doc.id}], "output_format": "png", **given}, state, None))
    assert out["error"] is None and out["count"] == 1, out
    (row,) = db.query(Rendition, document_id=doc.id)
    assert row.role == role and row.steps[0]["step"] == step and row.steps[0]["params"] == given
    assert open(doc.path, "rb").read() == before
