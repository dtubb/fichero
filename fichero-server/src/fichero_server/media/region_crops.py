"""Materialize a region node's own pixels.

A node that is a BAND of its parent — a diary entry on a page, a hand-drawn
crop — carries ``region_in_parent`` and shares its parent's file:
``crop_image_child_impl`` sets ``path=source.path``, and the in-app split does
the same. The region is real; the bytes are not. Nothing was ever written for
that node alone.

That is exactly why a tool cannot be run on an entry today. The vision fan-out
pairs ``files[i]`` with ``documents[i]``, and for a region node ``files[i]`` is
the whole page — so "run Detect Regions on this one entry" silently runs it on
everything around the entry too.

This module renders the band and persists it as a ``Rendition`` OF THE ENTRY,
so the entry has a picture of its own to hand a tool.

WHAT IT REFUSES, AND WHY EACH REFUSAL IS THE POINT

A crop is a NEW FRAME. Anything measured on it is a fraction of the crop, not
of the page, and the only reason that is safe is that the frame is recorded:
the rendition stores its pixel size, and geometry measured on it names it.

So a region that was itself measured on some OTHER rendition — a rotated or
deskewed picture — cannot be materialized here. Cropping the original at
fractions taken from a rotated frame yields a plausible band of the wrong part
of the page. Resolving that needs the rendition's transform, which is not
populated yet, so this raises instead of guessing. Pure crops only.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fichero_server.media.region_math import require_normalized
from fichero_server.models import Document, Rendition

logger = logging.getLogger(__name__)

#: Role for a rendition that is a node's own band of its parent.
REGION_CROP_ROLE = "region-crop"


class RegionCropUnavailable(Exception):
    """The band cannot be rendered, and guessing one would be worse.

    Raised rather than returned so a caller cannot mistake "could not crop"
    for "no crop needed" — those are different facts and the fan-out must
    treat them differently.
    """


def owns_its_pixels(document: Document, parent: Document | None) -> bool:
    """Whether ``document`` has a file of its own rather than its parent's.

    A region child is created with ``path=source.path``, so identity of path
    with the parent is what "no bytes of my own" actually looks like in this
    schema.
    """
    if not document.path:
        return False
    if parent is None or not parent.path:
        return True
    return Path(document.path) != Path(parent.path)


def existing_region_crop(db, document: Document) -> Rendition | None:
    """The crop already materialized for this node, if any.

    Idempotence is keyed on the node and the role rather than on a filename:
    ``_copy_to_library`` renames on collision, so a path-keyed check never
    matches and every re-run stacks another copy — a mistake this program has
    already made once.
    """
    for rendition in db.query(Rendition, document_id=document.id):
        if rendition.role == REGION_CROP_ROLE:
            return rendition
    return None


def materialize_region_crop(
    db,
    document: Document,
    library_path: str | Path | None,
) -> Rendition | None:
    """Render ``document``'s band of its parent and persist it as a Rendition.

    Returns None when there is nothing to do — the node is not a band, or it
    already owns its pixels. Returns the EXISTING rendition when the crop was
    already materialized. Raises ``RegionCropUnavailable`` when a crop is
    genuinely wanted and cannot be made honestly.
    """
    region = document.region_in_parent
    if region is None:
        return None  # not a band; the ordinary page case, untouched

    parent = db.get(Document, document.parent_id) if document.parent_id else None
    if owns_its_pixels(document, parent):
        return None  # already has a picture of its own

    existing = existing_region_crop(db, document)
    if existing is not None:
        return existing

    if region.rendition_id:
        raise RegionCropUnavailable(
            f"{document.id}'s region was measured on rendition "
            f"{region.rendition_id}, not the parent's original frame. Cropping "
            "the original at those fractions would cut a plausible band of the "
            "WRONG part of the page. Resolving it needs that rendition's "
            "transform, which is not recorded yet."
        )
    require_normalized(region, f"{document.id}'s region")

    if parent is None or not parent.path:
        raise RegionCropUnavailable(
            f"{document.id} is a band of a parent with no file to cut from"
        )
    source = Path(parent.path)
    if not source.is_file():
        raise RegionCropUnavailable(f"parent image missing on disk: {source}")

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment
        raise RegionCropUnavailable(f"Pillow unavailable: {exc}") from exc

    try:
        with Image.open(source) as image:
            width, height = image.size
            x, y, w, h = region.rect
            box = (
                int(round(x * width)), int(round(y * height)),
                int(round((x + w) * width)), int(round((y + h) * height)),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                raise RegionCropUnavailable(
                    f"{document.id}'s region is empty at the parent's size "
                    f"({width}x{height}): {region.rect}"
                )
            cropped = image.crop(box)
            crop_width, crop_height = cropped.size

            import tempfile

            suffix = source.suffix or ".png"
            with tempfile.TemporaryDirectory() as staging:
                staged = Path(staging) / f"{document.id}_region{suffix}"
                cropped.save(staged)

                from fichero_server.importers.ingest import _copy_to_library

                package = Path(library_path) if library_path else None
                stored = _copy_to_library(staged, package)
    except RegionCropUnavailable:
        raise
    except Exception as exc:
        raise RegionCropUnavailable(f"could not crop {document.id}: {exc}") from exc

    rendition = Rendition(
        document_id=document.id,
        role=REGION_CROP_ROLE,
        path=str(stored),
        produced_from=str(source),
        # The frame this crop IS. Recorded, never implied — the whole reason a
        # tool may safely measure against it.
        pixel_width=crop_width,
        pixel_height=crop_height,
        # NOT primary. Whether an entry should OPEN on its crop is a view
        # decision, and the ladder already expresses it by zooming the page.
        # A storage default that silently changed what the reader opens would
        # smuggle a product choice into a data field. The viewer chooses; the
        # rendition just exists.
        is_primary=False,
        note="the node's own band of its parent",
    )
    db.save(rendition)
    logger.info(
        "materialized region crop for %s: %sx%s from %s",
        document.id, crop_width, crop_height, source.name,
    )
    return rendition
