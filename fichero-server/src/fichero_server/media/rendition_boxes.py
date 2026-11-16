"""Every segment's box in the SHOWN rendition's pixels (#6420, `prep.preview-draws-segments-on-the-selected-rendition`).

The same carrying `compare_readings.frame_of` does for the page's current image, but for ANY one rendition of the page: the
Preview, showing a rendition, draws the page's segments on it from this answer instead of drawing none. A rendition whose place
on the photograph is not recorded gets no boxes and says so (`followed` false), never a guess.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SegmentsOnRendition(BaseModel):
    rendition_id: str
    image_width: int | None = None
    image_height: int | None = None
    followed: bool = Field(description="the segments' place on this rendition is known; false: no box is given")
    note: str | None = None
    boxes: dict[str, list[float]] = Field(default_factory=dict, description="segment id -> [x, y, w, h] in this rendition's pixels")


def segments_on_rendition(db: Any, doc: Any, rendition: Any, segments: list[Any]) -> SegmentsOnRendition:
    from fichero_server.db.storage import resolve_source
    from fichero_server.media.current_image import Unmappable, _absolute, _rendition_map, _size_of, _upright_size_of

    root = Path(db.path).parent
    photograph = resolve_source(doc, library_root=root)
    path = _absolute(root, rendition.path)
    if photograph is None or not path.is_file():
        return SegmentsOnRendition(rendition_id=rendition.id, followed=False, note="the page's picture or this rendition has no file here")
    try:
        carry = _rendition_map(db, rendition, photograph, _upright_size_of(photograph), root)
    except Unmappable as why:
        return SegmentsOnRendition(rendition_id=rendition.id, followed=False, note=f"the segments' place on this rendition is not known ({why})")
    width, height = _size_of(path)
    boxes: dict[str, list[float]] = {}
    for row in segments:
        if getattr(row, "deleted_at", None) is not None:
            continue
        rect = [row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h]
        moved = rect if carry is None else carry.carry_rect(rect)
        boxes[row.id] = [round(moved[0] * width, 2), round(moved[1] * height, 2), round(moved[2] * width, 2), round(moved[3] * height, 2)]
    return SegmentsOnRendition(rendition_id=rendition.id, image_width=int(width), image_height=int(height), followed=True, boxes=boxes)
