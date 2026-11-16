"""Split: a spread cut at its gutter into pages in reading order (`image.enhance.split-spread`, `media.page_split`).

`plan` is the decision (outline, gutter, pages); `run` returns the first page in reading order and the account carries every
page's box, so a door that writes all the pages (the `split_pages` node) reads `account["pages"]`."""
from __future__ import annotations

from typing import Any, Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from fichero_server.media import page_split

STEP = "split"


class Params(BaseModel):
    direction: Literal["ltr", "rtl"] = Field("ltr", description="Reading direction: the order the pages of a spread come out in.")
    use_apple_vision: bool = Field(True, description="Find the document with Apple Vision's outline; off, the whole image is the document.")
    min_confidence: float = Field(page_split.MIN_GUTTER_CONFIDENCE, ge=0.0, le=1.0,
                                  description="Below this gutter confidence a spread is proposed for review, not cut.")


def plan(image: Image.Image, params: Params, outline: page_split.Outline | None = None) -> dict[str, Any]:
    """Outline -> gutter -> pages for one image. `outline` is given by a caller that already ran Vision (the node does, under the
    engine's Vision gate); else Vision is asked here when `use_apple_vision`, and the whole frame is the outline when it finds none."""
    if outline is None and params.use_apple_vision:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as scratch:
            shot = Path(scratch) / "page.png"
            image.convert("RGB").save(shot)
            outline = page_split.detect_document_outline(str(shot))
    outline = outline or page_split.whole_frame(image.width, image.height)
    return page_split.split_plan_for_image(np.asarray(image.convert("L")), outline, direction=params.direction,
                                           min_confidence=params.min_confidence)


def run(image: Image.Image, params: Params, outline: page_split.Outline | None = None) -> tuple[Image.Image, dict[str, Any]]:
    account = {"step": "split", **plan(image, params, outline)}
    x, y, w, h = account["pages"][0]
    return image.crop((x, y, x + w, y + h)), account
