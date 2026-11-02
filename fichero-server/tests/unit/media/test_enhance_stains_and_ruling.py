"""Stain flattening and ruled-line handling as enhancement steps (`image.enhance.stain-flattening`, `image.enhance.ruled-lines`,
#6195). Fixtures are drawn, never the owner's scans. Each step is pressed through the engine function, the saved-edits and
preview routes, and the workflow node that writes the enhanced rendition."""
from __future__ import annotations

import asyncio
import io

import numpy as np
import pytest
from PIL import Image

from fichero_server.models import Document, FileType, Rendition

PAPER = np.array([228, 222, 205], "float32")


def _stained_page():
    """A paper page with six ink lines and a wide smooth stain on the right; returns (image, stain mask, clean mask, ink mask)."""
    h, w = 900, 1200
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((xx - 850) / 170.0) ** 2 + ((yy - 450) / 260.0) ** 2))  # wider than the kernel (1200 / 40 = 30 px)
    shade = 1.0 - 0.28 * blob
    arr = PAPER[None, None, :] * shade[:, :, None] + rng.normal(0, 2.0, (h, w, 1))
    ink = np.zeros((h, w), bool)
    for y in range(120, 800, 110):
        ink[y:y + 4, 60:1140] = True
    arr[ink] = arr[ink] * 0.13
    image = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"))
    stain = (blob > 0.7) & ~ink
    clean = (blob < 0.01) & ~ink & (xx < 500)
    return image, stain, clean, ink


def _grey(image):
    return np.asarray(image.convert("L"), "float32")


def test_stain_flatten_evens_the_stain_to_the_paper_and_keeps_the_ink_contrast():
    from fichero_server.media.enhance import stain_flatten

    image, stain, clean, ink = _stained_page()
    before = _grey(image)
    assert before[clean].mean() - before[stain].mean() > 40, "the fixture's stain is a real one"
    out, account = stain_flatten.run(image, stain_flatten.Params())
    after = _grey(out)
    assert abs(after[stain].mean() - after[clean].mean()) < 10, (after[stain].mean(), after[clean].mean())
    assert account["step"] == "stain-flatten" and account["kernel_divisor"] == 40
    ink_in_clean = ink.copy()
    ink_in_clean[:, 500:] = False
    near_clean = ink_in_clean[:, :500]
    before_gap = before[:, :500][clean[:, :500]].mean() - before[:, :500][near_clean].mean()
    after_gap = after[:, :500][clean[:, :500]].mean() - after[:, :500][near_clean].mean()
    assert after_gap > 0.9 * before_gap, (before_gap, after_gap)
    ink_in_stain = ink & (np.mgrid[0:900, 0:1200][1] > 700)
    assert after[clean].mean() - after[ink_in_stain].mean() > 0.9 * (before[clean].mean() - before[ink_in_stain].mean())


def test_stain_flatten_strength_zero_leaves_the_lightness_as_it_was_and_a_page_without_opencv_comes_back_unchanged():
    from fichero_server.media.enhance import stain_flatten

    image, *_ = _stained_page()
    out, _ = stain_flatten.run(image, stain_flatten.Params(strength=0.0))
    assert np.abs(_grey(out) - _grey(image)).max() <= 2


def _ruled_page():
    """Paper, green ruling every 30 px (2 px thick, full width), black text bars crossing it, and a thick green stamp."""
    h, w = 400, 600
    arr = np.full((h, w, 3), (236, 232, 218), "uint8")
    rules = np.zeros((h, w), bool)
    for y in range(40, 380, 30):
        rules[y:y + 2, :] = True
    arr[rules] = (90, 170, 100)
    ink = np.zeros((h, w), bool)
    for y in range(36, 380, 60):
        ink[y:y + 12, 100:480] = True  # text bars crossing a rule
    arr[ink] = (25, 25, 30)
    stamp = np.zeros((h, w), bool)
    stamp[344:366, 500:560] = True  # a 22 x 60 green block between two rules: thick and short, so not ruling
    arr[stamp] = (90, 170, 100)
    return Image.fromarray(arr), rules & ~ink & ~stamp, ink, stamp


def test_ruled_lines_fills_green_ruling_from_the_paper_and_leaves_ink_and_a_thick_green_block_alone():
    from fichero_server.media.enhance import ruled_lines

    image, rules, ink, stamp = _ruled_page()
    out, account = ruled_lines.run(image, ruled_lines.Params())
    before, after = np.asarray(image, int), np.asarray(out, int)
    paper = np.array([236, 232, 218])
    assert np.abs(before[rules] - paper).mean() > 60, "the fixture's ruling is visible"
    assert np.abs(after[rules] - paper).mean() < 12, np.abs(after[rules] - paper).mean()
    assert np.array_equal(after[ink], before[ink]), "the ink's pixels are unchanged"
    core = np.zeros_like(stamp)
    core[347:363, 504:556] = True  # the block's inside: the fill reaches one pixel past a rule, not into the block
    assert np.array_equal(after[core], before[core]), "a thick, short green block is not ruling"
    assert account["step"] == "ruled-lines" and account["colour"] == "green" and account["pixels"] > 0


def test_ruled_lines_colour_none_and_a_page_without_ruling_are_returned_as_they_were():
    from fichero_server.media.enhance import ruled_lines

    image, *_ = _ruled_page()
    assert ruled_lines.run(image, ruled_lines.Params(colour="none"))[0].tobytes() == image.tobytes()
    plain = Image.new("RGB", (300, 200), (236, 232, 218))
    assert ruled_lines.run(plain, ruled_lines.Params())[0].tobytes() == plain.tobytes()
    blue = np.asarray(image).copy()
    blue[(blue == (90, 170, 100)).all(axis=2)] = (70, 90, 200)
    out, account = ruled_lines.run(Image.fromarray(blue), ruled_lines.Params())
    assert account["colour"] == "blue" and np.abs(np.asarray(out, int)[40:42, 10:90] - [236, 232, 218]).mean() < 12


def _document(db, image, name):
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    doc = Document(name=name, path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


@pytest.mark.parametrize("op, build, params", [
    ("stain_flatten", lambda: _stained_page()[0], {"strength": 1.0}),
    ("ruled_lines", lambda: _ruled_page()[0], {"colour": "green"}),
])
def test_a_saved_row_is_validated_and_previews_through_the_routes_and_a_bad_value_is_refused(client, db, op, build, params):
    image = build()
    doc = _document(db, image, f"{op}.png")
    refused = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": op, "params": {"strength": 5} if op == "stain_flatten" else {"colour": "pink"}}]})
    assert refused.status_code == 422, refused.text
    put = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": op, "params": params}]})
    assert put.status_code == 200, put.text
    got = client.get(f"/api/images/{doc.id}/preview")
    assert got.status_code == 200, got.text[:200]
    shown = Image.open(io.BytesIO(got.content)).convert("RGB")
    assert np.abs(np.asarray(shown, int) - np.asarray(image.convert("RGB"), int)).mean() > 0.5, "the preview shows the step"


@pytest.mark.parametrize("tool, step, build, given", [
    ("stain_flatten_images", "stain-flatten", lambda: _stained_page()[0], {"kernel_divisor": 30}),
    ("ruled_lines_images", "ruled-lines", lambda: _ruled_page()[0], {"colour": "green"}),
])
def test_the_node_writes_an_enhanced_rendition_that_records_the_step_and_its_settings(db, tool, step, build, given):
    from fichero_server.workflows.registry import get_tool_def
    from fichero_server.workflows.tools import enhance_step_nodes

    image = build()
    doc = _document(db, image, f"{tool}.png")
    before = open(doc.path, "rb").read()
    state = {"library_path": str(db.path.parent), "run_id": "run-1", "batch_id": "batch-1"}
    out = asyncio.run(getattr(enhance_step_nodes, tool)(
        {"files": [doc.path], "documents": [{"id": doc.id}], "output_format": "png", **given}, state, None))
    assert out["error"] is None and out["count"] == 1, out
    (row,) = db.query(Rendition, document_id=doc.id)
    assert row.role == "enhanced" and row.producer_run_id == "run-1"
    assert row.steps == [{"step": step, "params": given, "card": {"method": step, "model_id": None}}]
    assert open(doc.path, "rb").read() == before, "the source is untouched"
    assert get_tool_def(tool).config_schema["output_format"]["default"] == "jpg"
    assert {r["operation"]["op"] for r in out["image_edit_operations"]} == {step.replace("-", "_")}
