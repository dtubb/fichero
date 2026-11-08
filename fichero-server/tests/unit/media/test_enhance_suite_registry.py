"""Every enhancement step in the registry has a workflow node and an editor operation, and the same values give the same pixels
through both (`image.enhance.every-step-is-a-recipe-step-and-an-editor-control`, #6185). The Adjust control is a Swift
test (`ImageEditAdjustControlsTests.swift`)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from fichero_server.media.enhance import STEPS

#: step -> (workflow node, editor operation) for the steps that are an ADJUSTMENT of a page's pixels. The page-level steps
#: (page-crop, split) change which pages exist and are reached by their own routes and nodes.
ADJUSTMENTS = {
    "rotate": ("rotate_images", "rotate"), "deskew": ("deskew_images", "straighten"), "contrast": ("contrast_images", "contrast"),
    "stain-flatten": ("stain_flatten_images", "stain_flatten"), "ruled-lines": ("ruled_lines_images", "ruled_lines"),
    "bleed-through": ("bleed_through_images", "bleed_through"), "denoise": ("denoise_images", "denoise"),
    "binarise": ("binarise_images", "binarise"),
}
#: The steps that are not yet a node of their own or an editor operation of their own, named so a new step cannot slip past.
NOT_YET = {"yellowing", "sharpen"}  # a node each (`yellowing_images`, `sharpen_images`); no editor operation of their own: they run inside Auto Enhance
PAGE_LEVEL = {"page-crop", "split"}


def test_every_step_is_an_adjustment_a_page_level_step_or_named_as_not_yet():
    assert set(STEPS) == set(ADJUSTMENTS) | NOT_YET | PAGE_LEVEL


@pytest.mark.parametrize("step", sorted(ADJUSTMENTS))
def test_an_adjustment_has_a_node_and_an_editor_operation_whose_request_is_its_params_model(step):
    from fichero_server.api.routes.ingest import image_editing
    from fichero_server.workflows.registry import get_tool_def

    node, op = ADJUSTMENTS[step]
    assert get_tool_def(node) is not None
    request = image_editing._OPERATION_MODELS[op]
    assert issubclass(request, STEPS[step].params)


@pytest.mark.parametrize("step, op, params", [
    ("denoise", "denoise", {"radius": 5, "speck": 3}),
    ("binarise", "binarise", {"method": "adaptive", "block": 21, "c": 3}),
    ("stain-flatten", "stain_flatten", {"kernel_divisor": 30, "strength": 0.5}),
    ("contrast", "contrast", {"clip": 3.0}),
])
def test_the_same_values_give_the_same_pixels_through_the_step_and_the_editor_operation(step, op, params):
    from fichero_server.media.image_ops import apply_operation

    rng = np.random.default_rng(1)
    image = Image.fromarray(rng.integers(0, 255, (120, 160, 3), dtype="uint8"))
    direct = STEPS[step].run(image, STEPS[step].params(**params))[0]
    assert apply_operation(image, {"op": op, "params": params}).tobytes() == direct.tobytes()


#: chain name -> the node that runs it, where the node is not `<name>_images`.
NODE_OF = {"straighten": "deskew_images", "flip_horizontal": "flip_images", "flip_vertical": "flip_images"}
#: chain names with no workflow node yet, named so a new chain operation cannot slip past (`image.ops.workflow-node-per-operation`, #6363).
NO_NODE_YET = {"brightness", "crop", "mark_blank", "square"}  # square needs a page's four corners; the rest have no standalone node


def test_every_chain_operation_has_a_workflow_node_or_is_named_as_not_yet():
    from fichero_server.api.routes.ingest import image_editing
    from fichero_server.workflows.registry import get_tool_def

    import fichero_server.workflows.tools.enhance_step_nodes  # noqa: F401  (registers the step nodes)

    names = image_editing._OPERATION_MODELS.keys() | image_editing._PARAMETERLESS_OPERATIONS
    missing = {n for n in names if get_tool_def(NODE_OF.get(n, f"{n}_images")) is None}
    assert missing == NO_NODE_YET, f"chain operations with no node (and not named): {missing - NO_NODE_YET}; named but now have one: {NO_NODE_YET - missing}"


def _tinted() -> Image.Image:
    pixels = np.full((60, 80, 3), (225, 215, 150), "uint8")  # a yellowed page
    pixels[10:14, 10:70] = (40, 35, 30)
    pixels[:, :5] = (200, 40, 40)  # a coloured edge, so a mirror shows
    return Image.fromarray(pixels)


@pytest.mark.parametrize("tool, step, given", [
    ("yellowing_images", "yellowing", {}), ("sharpen_images", "sharpen", {"amount": 2.0}), ("flip_images", "flip", {"direction": "vertical"}),
    ("grayscale_images", "grayscale", {}), ("auto_levels_images", "auto-levels", {}),
])
def test_a_new_node_runs_its_step_and_names_it_in_the_rendition_row(tmp_path, tool, step, given):
    from fichero_server.workflows.registry import get_tool_def
    from fichero_server.workflows.tools.enhance_step_nodes import step_image_file

    assert get_tool_def(tool) is not None
    source = tmp_path / "a.png"
    _tinted().save(source)
    result = step_image_file(step, source, tmp_path / "out", output_format="png", **given)
    assert result["error"] is None, result
    assert result["steps"][0]["step"] == step and result["steps"][0]["params"] == given
    assert Image.open(result["outputs"][0]).tobytes() != _tinted().tobytes()


def test_flip_goes_the_way_it_is_told_and_grayscale_leaves_no_colour(tmp_path):
    from fichero_server.workflows.tools.enhance_step_nodes import step_image_file

    source = tmp_path / "a.png"
    _tinted().save(source)
    mirrored = np.asarray(Image.open(step_image_file("flip", source, tmp_path / "h", output_format="png", direction="horizontal")["outputs"][0]))
    assert (mirrored[:, -5:] == (200, 40, 40)).all() and (mirrored[:, :5] != (200, 40, 40)).any()
    flipped = np.asarray(Image.open(step_image_file("flip", source, tmp_path / "v", output_format="png", direction="vertical")["outputs"][0]))
    assert (flipped[10:14] != (40, 35, 30)).any() and (flipped[46:50, 10:70] == (40, 35, 30)).all()
    gray = np.asarray(Image.open(step_image_file("grayscale", source, tmp_path / "g", output_format="png")["outputs"][0]))
    assert (gray[..., 0] == gray[..., 1]).all() and (gray[..., 1] == gray[..., 2]).all()


#: chain names with no Prepare Images operation of their own, named so a new chain operation cannot slip past
#: (`image.ops.matrix-is-complete`, #6363). Ruled lines and bleed-through are run by the paper answers; the rest are editor-only.
NO_PREPARE_YET = {"adaptive_binarize", "auto_crop_border", "bleed_through", "brightness", "enhance", "fuzzy_clean", "mark_blank",
                  "remove_background", "rotate", "ruled_lines", "segment", "square"}


def test_the_operation_matrix_is_complete_or_names_what_is_not_yet():
    """One walk of the chain vocabulary: each operation has its action, its node and its Prepare operation id, or is named here as
    not yet (`image.ops.matrix-is-complete`). A new operation added without all the doors fails this naming the missing ones."""
    from fichero_server.media.image_op_matrix import missing_doors

    missing = missing_doors()
    assert missing["action"] == set(), f"chain operations with no image.<op> action: {missing['action']}"
    no_node, no_prepare = missing["node"], missing["prepare"]
    assert no_node == NO_NODE_YET, f"no node: new {no_node - NO_NODE_YET}; named but now have one {NO_NODE_YET - no_node}"
    assert no_prepare == NO_PREPARE_YET, f"no Prepare id: new {no_prepare - NO_PREPARE_YET}; named but now have one {NO_PREPARE_YET - no_prepare}"


def test_a_new_operation_without_its_doors_fails_the_matrix_naming_them(monkeypatch):
    from fichero_server.api.routes.ingest import image_editing
    from fichero_server.media.image_op_matrix import missing_doors

    monkeypatch.setitem(image_editing._OPERATION_MODELS, "noop", image_editing._OPERATION_MODELS["denoise"])
    assert all("noop" in doors for doors in missing_doors().values())
