"""One upright frame (`prep.image.one-upright-frame`, Test 14, ## 1114).

A phone photo carries its rotation as an EXIF Orientation tag. New geometry (Kraken's lines and regions, and the segments
made from them) is measured on the page as a person sees it, the tag applied once, and says so with `frame: "upright"`.
Geometry with NO marker was measured on the file's raw pixels (every pass before this), and is cut from the raw pixels
still: nothing is rewritten, so an old pass on a rotated page keeps matching its own image. Every place that pairs a page
image with geometry opens the image through `open_in_frame`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

FRAME_UPRIGHT = "upright"


def upright(image: Any) -> Any:
    """The page as a person sees it, RGB: the EXIF Orientation applied once."""
    from PIL import ImageOps

    out = ImageOps.exif_transpose(image) or image
    return out if out.mode == "RGB" else out.convert("RGB")


def upright_size(image: Any) -> tuple[int, int]:
    """(width, height) in the upright frame, from the header alone: orientations 5-8 turn the page a quarter."""
    width, height = image.size
    return (height, width) if (image.getexif().get(0x0112, 1) or 1) in (5, 6, 7, 8) else (width, height)


def open_in_frame(path: str | Path, frame: str | None, *, mode: str | None = None) -> Any:
    """The image at `path`, loaded, in the frame the geometry was measured on: upright when `frame` says so, else the
    file's raw pixels (geometry with no marker). `mode` converts it ("RGB", "RGBA", "L") when given."""
    from PIL import Image

    with Image.open(path) as opened:
        image = upright(opened) if frame == FRAME_UPRIGHT else opened.copy()
        image.load()
    return image.convert(mode) if mode and image.mode != mode else image


def frame_of(*carriers: Any) -> str | None:
    """The frame marker on the first of these (a result's or box's or segment's metadata dict) that has one."""
    for carrier in carriers:
        value = (carrier or {}).get("frame") if isinstance(carrier, dict) else None
        if value:
            return str(value)
    return None


def mark(boxes: list[Any]) -> None:
    """Say on each box that it was measured on the upright page."""
    for box in boxes:
        box.metadata["frame"] = FRAME_UPRIGHT


def copy_in_frame(source: Path, dest: Path, frame: str | None) -> None:
    """Copy the page file to `dest` in the frame its geometry was measured on: a byte copy unless the geometry is upright
    and the file carries an orientation, in which case the upright pixels are written (tag gone), so an exported
    page and its lines agree whatever reads the pair."""
    import shutil

    from PIL import Image

    if frame == FRAME_UPRIGHT:
        with Image.open(source) as opened:
            if (opened.getexif().get(0x0112, 1) or 1) != 1:
                image = upright(opened)
                image.save(dest, format=opened.format or "PNG", **({"quality": 95} if opened.format == "JPEG" else {}))
                return
    shutil.copy2(source, dest)


def pass_frame(db: Any, pass_ref: Any) -> str | None:
    """The frame a pass was measured on: its source result's marker (`ocr_geometry.metadata["frame"]`). A person's split, create
    or merge inside the pass has no marker of its own and inherits this one. None for a pass with no marker (raw pixels)."""
    from fichero_server.models import Artifact
    from fichero_server.models.segments import SegmentPass

    row = db.get(SegmentPass, pass_ref) if isinstance(pass_ref, str) else pass_ref
    artifact_id = getattr(row, "source_artifact_id", None)
    artifact = db.get(Artifact, artifact_id) if artifact_id else None
    geometry = getattr(artifact, "ocr_geometry", None)
    return frame_of(getattr(geometry, "metadata", None))


def region_frame(region: Any) -> str | None:
    """The frame a node's region (`NodeRegion`) was measured on, from its `frame` extra; None = the file's raw pixels."""
    extra = getattr(region, "model_extra", None) or {}
    return frame_of(extra, {"frame": getattr(region, "frame", None)})


def frame_of_lines(db: Any, pass_ref: Any, segments: Any) -> str | None:
    """The frame of a pass's lines: the pass's own marker first (a person's split, create or merge, listed first, has none of
    its own), else the first segment that has one. None = the file's raw pixels."""
    return pass_frame(db, pass_ref) or frame_of(*(getattr(s, "metadata", None) for s in segments))
