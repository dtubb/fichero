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
NOT_YET = {"yellowing", "sharpen"}  # reached by the contrast/enhance clahe method and the Sharpness operation today
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
