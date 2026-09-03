"""One owner for "this format has no alpha — what shows through?".

JPEG (and any other opaque encode) cannot carry transparency, so every writer
has to decide what replaces it. The decision was made independently in a dozen
places and every one of them made it the same wrong way::

    if image.mode in {"RGBA", "P"}:
        image = image.convert("RGB")

``convert("RGB")`` does not composite. It DROPS the alpha channel and keeps
whatever colour sits underneath — which for a background-removed image is
(0, 0, 0). So every cut-out came back on a BLACK ground: thumbnails, display
renditions, and every workflow tool that re-encoded one (Daniel, 2026-09-02).

Standing ruling: transparent flattens to plain WHITE.

Compositing rather than dropping also keeps ANTI-ALIASED edges honest — a
half-transparent edge pixel blends toward white instead of snapping to the
black underneath it. That is the part a "if fully transparent, paint white"
shortcut gets wrong, and it is why this is a composite and not a fill.

PIL is imported inside the function on purpose: ``db/storage.py`` is on the
engine's startup path and lazy-loads Pillow (``_load_pil()``), so a
module-level ``from PIL import Image`` here would undo that.
"""

from __future__ import annotations

from typing import Any

#: What transparency becomes. Daniel's ruling, in one place.
FLATTEN_BACKGROUND = (255, 255, 255)


def has_transparency(image: Any) -> bool:
    """Whether this image carries alpha that a flatten would have to resolve.

    Palette images are the trap: a P-mode PNG carries transparency in a tRNS
    chunk, not in its mode name, so a ``mode in {"RGBA"}`` check misses it and
    the image silently flattens to black anyway.
    """
    return image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )


def flatten_for_opaque_format(image: Any) -> Any:
    """Return an image an alpha-less format can hold, transparency over WHITE.

    A no-op for images that are already opaque, so it is safe to call on any
    save path without first asking what mode the image is in — which is the
    point: the check and the fix travel together instead of every caller
    re-deriving the condition and getting it subtly different.
    """
    from PIL import Image

    if image.mode in ("RGB", "L"):
        return image
    if has_transparency(image):
        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (*FLATTEN_BACKGROUND, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    return image.convert("RGB")
