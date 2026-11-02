"""Each enhancement step is one engine function reached by every door (`image.enhance.three-doors-one-function`,
`image.enhance.old-conventions-left-behind`, #6194).

The steps that exist in the engine today are page-crop, deskew, rotate, split, contrast, yellowing and sharpen. Stains, ruled lines and
show-through have no engine code yet (#6195 and the steps after it) and so no module here. Every door is pressed for
real (the editor's routes, the node's file function, the page-crop run); a spy on the step's `run` proves the door
reached it. Fixtures are drawn, never the owner's scans.
"""
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pydantic import BaseModel

from fichero_server.models import DocType, Document, FileType

STEPS = ["page_crop", "deskew", "rotate", "split", "contrast", "yellowing", "sharpen"]
SRC = Path(__file__).resolve().parents[3] / "src" / "fichero_server"


def _ruled(w=240, h=160) -> Image.Image:
    arr = np.full((h, w, 3), 235, "uint8")
    arr[40:44, 20:220] = 20
    arr[90:94, 20:220] = 20
    return Image.fromarray(arr)


def _doc(db, name="p.png", image=None) -> Document:
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    (image or _ruled()).save(path)
    doc = Document(name=name, path=str(path), file_type=FileType.image)
    db.save(doc)
    return doc


def _spy(monkeypatch, module_name):
    module = importlib.import_module(f"fichero_server.media.enhance.{module_name}")
    calls = []
    real = module.run

    def spy(image, params, *args, **kwargs):
        calls.append(params)
        return real(image, params, *args, **kwargs)

    monkeypatch.setattr(module, "run", spy)
    return calls


# --- one function per step -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("step", STEPS)
def test_a_step_is_one_module_with_run_taking_image_and_params_and_returning_image_and_account(step):
    module = importlib.import_module(f"fichero_server.media.enhance.{step}")
    assert issubclass(module.Params, BaseModel)
    assert list(inspect.signature(module.run).parameters)[:2] == ["image", "params"]
    image, account = module.run(_ruled(), module.Params(**{"rotate": {"angle": 90}, "split": {"use_apple_vision": False},
                                                            "page_crop": {"vision": False}}.get(step, {})))
    assert isinstance(image, Image.Image) and isinstance(account, dict) and account["step"] == step.replace("_", "-")


def test_the_registry_names_every_step_with_its_params_model():
    from fichero_server.media import enhance

    assert set(enhance.STEPS) == {"page-crop", "deskew", "rotate", "split", "contrast", "yellowing", "sharpen"}
    for name, spec in enhance.STEPS.items():
        assert issubclass(spec.params, BaseModel) and callable(spec.run)


def test_rotate_run_turns_a_quarter_without_resampling_and_a_fraction_with_expand():
    from fichero_server.media.enhance import rotate

    image = _ruled(80, 50)
    turned, account = rotate.run(image, rotate.Params(angle=90))
    assert turned.size == (50, 80) and turned.tobytes() == image.transpose(Image.Transpose.ROTATE_90).tobytes()
    assert account["method"] == "quarter-turn" and account["angle"] == 90.0
    tilted, account = rotate.run(image, rotate.Params(angle=3.0))
    assert tilted.size != image.size and account["method"] == "rotate"


def test_deskew_run_turns_a_tilted_page_back_and_a_square_one_is_left_alone():
    from fichero_server.media.enhance import deskew

    page = _ruled(600, 400)
    straight, account = deskew.run(page, deskew.Params())
    assert account["angle"] == 0.0 and straight.tobytes() == page.tobytes()
    tilted = page.rotate(-4, expand=True, fillcolor=(235, 235, 235))
    out, account = deskew.run(tilted, deskew.Params())
    assert abs(account["angle"]) >= 0.3 and account["method"] == "hough"


def test_split_run_cuts_a_spread_at_the_dark_gutter_and_reports_every_page():
    from fichero_server.media.enhance import split

    arr = np.full((300, 400, 3), 230, "uint8")
    arr[:, 196:204] = 60
    first, account = split.run(Image.fromarray(arr), split.Params(use_apple_vision=False))
    assert account["decision"] == "split" and len(account["pages"]) == 2
    assert first.size == (account["pages"][0][2], account["pages"][0][3])


def test_contrast_run_matches_the_clahe_function_it_wraps_and_the_old_factor_still_means_pil_contrast():
    from fichero_server.media.enhance import contrast
    from fichero_server.media.image_ops import apply_clahe_contrast

    image = _ruled()
    out, account = contrast.run(image, contrast.Params(clip=3.0, tile=8))
    assert out.tobytes() == apply_clahe_contrast(image, clip=3.0, tile=8).tobytes() and account["method"] == "clahe"
    out, account = contrast.run(image, contrast.Params(factor=1.5))
    assert account["method"] == "pil-contrast" and out.tobytes() != image.tobytes()


# --- the doors ---------------------------------------------------------------------------------------------------------

def test_editor_rotate_route_reaches_the_rotate_step(client, db, monkeypatch):
    calls = _spy(monkeypatch, "rotate")
    doc = _doc(db)
    r = client.post(f"/api/images/{doc.id}/operations/rotate", json={"angle": 90, "expand": True, "page": 1})
    assert r.status_code == 200, r.text
    assert [(c.angle, c.expand) for c in calls] == [(90.0, True)]


def test_editor_straighten_route_reaches_the_deskew_step(client, db, monkeypatch):
    calls = _spy(monkeypatch, "deskew")
    doc = _doc(db)
    r = client.post(f"/api/images/{doc.id}/operations/straighten", json={"page": 1})
    assert r.status_code == 200, r.text
    assert len(calls) == 1


@pytest.mark.parametrize("found, recorded", [(0.1, 0.0), (2.0, 2.0)])
def test_editor_straighten_records_the_angle_deskew_found_and_leaves_a_page_under_the_minimum_unturned(
        client, db, monkeypatch, found, recorded):
    monkeypatch.setattr("fichero_server.media.image_ops.detect_deskew_angle", lambda image: found)
    doc = _doc(db)
    r = client.post(f"/api/images/{doc.id}/operations/straighten", json={"page": 1})
    assert r.status_code == 200, r.text
    assert r.json()["operations"][0]["params"]["angle"] == recorded


def test_editor_chain_preview_of_a_contrast_row_reaches_the_contrast_step(client, db, monkeypatch):
    calls = _spy(monkeypatch, "contrast")
    doc = _doc(db)
    put = client.put(f"/api/images/{doc.id}/edits", json={"operations": [{"op": "contrast", "params": {"clip": 3.0}}]})
    assert put.status_code == 200, put.text
    assert client.get(f"/api/images/{doc.id}/preview").status_code == 200
    assert calls and all(c.clip == 3.0 for c in calls)


def test_rotate_node_file_function_reaches_the_rotate_step(tmp_path, monkeypatch):
    from fichero_server.workflows.tools.rotate_images import rotate_image_file

    calls = _spy(monkeypatch, "rotate")
    source = tmp_path / "a.png"
    _ruled(80, 50).save(source)
    result = rotate_image_file(source, tmp_path, rotation_degrees=90, auto_orient=False, output_format="png")
    assert result["error"] is None and Image.open(result["outputs"][0]).size == (50, 80)
    assert [c.angle for c in calls] == [270.0]  # clockwise 90 is PIL's counter-clockwise 270


def test_split_node_file_function_reaches_the_split_step(tmp_path, monkeypatch):
    from fichero_server.workflows.tools.split_pages import split_pages_file

    calls = _spy(monkeypatch, "split")
    arr = np.full((300, 400, 3), 230, "uint8")
    arr[:, 196:204] = 60
    source = tmp_path / "spread.png"
    Image.fromarray(arr).save(source)
    result = split_pages_file(source, tmp_path / "out", use_apple_vision=False)
    assert result["error"] is None and len(result["outputs"]) == 2 and len(calls) == 1


def test_deskew_node_measures_with_the_deskew_step(client, db, monkeypatch, tmp_path):
    import asyncio

    from fichero_server.workflows.tools import deskew_images as node
    from fichero_server.media.enhance import deskew

    seen = []
    real = deskew.measure
    monkeypatch.setattr(deskew, "measure", lambda image, params: seen.append(params) or real(image, params))
    doc = _doc(db, image=_ruled(600, 400).rotate(-4, expand=True, fillcolor=(235, 235, 235)))
    out = asyncio.run(node.deskew_images({"library_path": str(db.path.parent), "documents": [{"id": doc.id}]}, {}, None))
    assert seen, out


def test_the_batch_preview_of_a_turn_reaches_the_rotate_step(client, db, monkeypatch):
    calls = _spy(monkeypatch, "rotate")
    folder = Document(name="f", doc_type=DocType.folder)
    db.save(folder)
    doc = _doc(db)
    doc.parent_id = folder.id
    db.save(doc)
    got = client.post("/api/images/batch-prepare/preview", json={"folder_id": folder.id, "operation": {"op": "rotate", "angle": 90}})
    assert got.status_code == 200, got.text
    assert got.json()["pages"] == 1 and [c.angle for c in calls] == [90.0]


def test_the_contrast_node_is_registered_with_its_config_from_the_params_model():
    from fichero_server.media.enhance import contrast
    from fichero_server.workflows.registry import get_tool_def

    config = get_tool_def("contrast_images").config_schema
    for key, field in contrast.Params.model_fields.items():
        assert config[key].get("default") == field.default
    assert config["clip"]["minimum"] == 1.0 and config["clip"]["maximum"] == 4.0
    assert config["profile"]["enum"] == ["handwritten", "typescript"]


def test_the_contrast_node_runs_the_contrast_step_and_writes_an_enhanced_rendition(db, monkeypatch):
    import asyncio

    from fichero_server.workflows.tools import contrast_images

    calls = _spy(monkeypatch, "contrast")
    doc = _doc(db)
    state = {"library_path": str(db.path.parent)}
    out = asyncio.run(contrast_images.contrast_images(
        {"files": [doc.path], "documents": [{"id": doc.id}], "clip": 3.0, "output_format": "png"}, state, None))
    assert out["error"] is None and out["count"] == 1, out
    assert [c.clip for c in calls] == [3.0]
    assert Image.open(out["output_files"][0]).tobytes() != _ruled().tobytes()


def test_the_rotate_node_config_has_the_params_models_angle_and_expand_and_the_node_turns_by_the_angle(tmp_path, monkeypatch):
    from fichero_server.workflows.tools.rotate_images import ROTATE_IMAGES_CONFIG, rotate_image_file

    assert ROTATE_IMAGES_CONFIG["angle"]["minimum"] == -360.0 and ROTATE_IMAGES_CONFIG["angle"]["maximum"] == 360.0
    assert ROTATE_IMAGES_CONFIG["expand"]["default"] is True
    calls = _spy(monkeypatch, "rotate")
    source = tmp_path / "a.png"
    _ruled(80, 50).save(source)
    result = rotate_image_file(source, tmp_path, angle=5.0, expand=False, auto_orient=False, output_format="png")
    assert result["error"] is None and [(c.angle, c.expand) for c in calls] == [(5.0, False)]
    assert Image.open(result["outputs"][0]).size == (80, 50)


def test_page_crop_run_finds_the_page_through_the_one_function(db, monkeypatch, tmp_path):
    from fichero_server.media.enhance import page_crop
    from fichero_server.recipes.page_crop import crop_pages

    calls = _spy(monkeypatch, "page_crop")
    mount = np.full((400, 600, 3), 10, "uint8")
    mount[60:340, 90:520] = 225
    doc = _doc(db, "mount.png", Image.fromarray(mount))
    account = crop_pages(db, [doc.id], "run-1")
    assert account["pages"] == 1 and len(calls) == 1
    assert isinstance(calls[0], page_crop.Params)


# --- one params model: editor schema, node config -------------------------------------------------------------------------

@pytest.mark.parametrize("request_name, step", [
    ("RotateOperationRequest", "rotate"),
    ("ContrastOperationRequest", "contrast"),
    ("StraightenOperationRequest", "deskew"),
])
def test_the_editor_request_schema_is_the_params_model_plus_the_page(request_name, step):
    from fichero_server.api.routes.ingest import image_editing

    params = importlib.import_module(f"fichero_server.media.enhance.{step}").Params
    request = getattr(image_editing, request_name)
    assert issubclass(request, params)
    schema, base = request.model_json_schema()["properties"], params.model_json_schema()["properties"]
    assert {k: v for k, v in schema.items() if k != "page"} == base
    assert "page" in schema


def test_the_split_node_config_comes_from_the_params_model():
    from fichero_server.media.enhance import split
    from fichero_server.workflows.tools.split_pages import SPLIT_PAGES_CONFIG

    for key, field in split.Params.model_fields.items():
        entry = SPLIT_PAGES_CONFIG[key]
        assert entry["default"] == field.default and entry["description"] == field.description
    assert SPLIT_PAGES_CONFIG["direction"]["enum"] == ["ltr", "rtl"]
    assert SPLIT_PAGES_CONFIG["min_confidence"]["minimum"] == 0.0 and SPLIT_PAGES_CONFIG["min_confidence"]["maximum"] == 1.0


# --- the old conventions are left behind ------------------------------------------------------------------------------

#: The step code and the nodes that call it. `importers/legacy_10_archive.py` reads an old archive's `assets/<stage>/`
#: folders on purpose (it is the importer of that archive, not an enhancement step) and is outside this list.
STEP_FILES = (
    [p for p in (SRC / "media").rglob("*.py")]
    + [SRC / "workflows" / "tools" / n for n in (
        "rotate_images.py", "deskew_images.py", "split_pages.py", "split_images.py", "enhance_images.py",
        "prepare_images.py", "auto_crop_border_images.py", "remove_background_images.py", "denoise_images.py",
        "adaptive_binarize_images.py", "fuzzy_clean_images.py")]
    + [SRC / "recipes" / "page_crop.py"]
)


def test_no_engine_module_imports_fichero_archive():
    offenders = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            offenders += [f"{path.relative_to(SRC)}: {n}" for n in names if n.split(".")[0] == "fichero_archive"]
    assert offenders == [], f"the engine must not import from fichero_archive: {offenders}"


def test_no_enhancement_step_reads_or_writes_an_assets_stage_folder_or_a_stage_manifest():
    offenders = []
    for path in STEP_FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if text == "assets" or text.startswith("assets/") or "/assets/" in text or text.endswith("_manifest.jsonl"):
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}: {text!r}")
    assert offenders == [], f"an enhancement step must not use an assets/<stage>/ folder or a stage manifest: {offenders}"


def test_a_stored_contrast_row_out_of_range_still_previews_as_it_was_saved(client, db):
    from fichero_server.models import ImageEditChain

    doc = _doc(db)
    # An old library holds this row; the save route would now refuse it (422), so it goes in the table directly.
    db.save(ImageEditChain(document_id=doc.id, operations=[{"op": "contrast", "params": {"factor": 12, "clip": 6.0}}]))
    assert client.get(f"/api/images/{doc.id}/preview").status_code == 200
