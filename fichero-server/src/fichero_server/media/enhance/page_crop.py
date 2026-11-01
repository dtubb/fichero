"""Page crop: the paper found on a photograph (`media.find_page`, no model) and cut out; a page the finder is not sure of keeps
the whole frame (`image.enhance.page-crop-writes-page-box`, #6188). `recipes.page_crop.crop_pages` (the run that writes
`page_box` and the crop rendition) decides through this `run`; it never calls the finder itself."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

STEP = "page-crop"


class Params(BaseModel):
    vision: bool = Field(True, description="Ask Apple Vision's outline first; off, only the contour finder answers.")
    min_confidence: float = Field(0.8, ge=0.0, le=1.0, description="A contour box is trusted only at this paper fill or above.")
    min_share: float = Field(0.15, ge=0.0, le=1.0, description="A box smaller than this share of the image is a stamp or a card, not the page.")


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    """The paper cut out when the finder is sure, else the image itself. The account: `trusted`, `box` (fractions of the
    image), `method`, `confidence`, `furniture`, `quad`; `found` is the finder's own `PageFound` (not JSON) for the caller that
    records it."""
    from fichero_server.media.find_page import find_page

    found = find_page(image) if params.vision else find_page(image, vision=False)
    # The contour finder's confidence is its paper fill; Vision's was gated by the finder (0.5), so only the contour's is tested here.
    unsure = found is not None and found.method == "contour" and found.confidence < params.min_confidence
    trusted = found is not None and not unsure and found.box[2] * found.box[3] >= params.min_share
    account: dict[str, Any] = {"step": "page-crop", "found": found, "unsure": unsure, "trusted": trusted,
                               "box": list(found.box) if found else None, "method": found.method if found else None,
                               "confidence": found.confidence if found else None}
    if not trusted:
        return image, account
    left, top, right, bottom = found.pixels(image.width, image.height)
    return image.crop((left, top, right, bottom)), account
