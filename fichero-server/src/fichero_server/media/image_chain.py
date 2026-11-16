"""The page's image chain in words (`wide.chain.served-by-the-engine`, #6296, #5386; section E of wide-onboarding.md).

What Prepare Images (and any other step that writes a picture of a page) made of it, in the order it was made: the photograph,
then each rendition with its operation's name and the figure in words, which one every later step reads (`current_page_image`,
the one rule), and each rendition passed over with the reason. The app draws this and works none of it out; Preview's rendition
axis (`rendition_order.order_renditions`) is served beside it so the two never disagree.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

#: The rank of a rendition's role in the order Prepare Images writes them: the tiebreak when two share a second.
_MADE_ORDER = ("crop", "squared", "flattened", "rotated", "deskewed", "prepared")
#: The operation each role belongs to, in the words of the Set Up rows (`recipes/prepare_operations.py`).
_OPERATION = {"crop": "Crop to the paper", "squared": "Crop to the paper", "flattened": "Crop to the paper",
              "rotated": "Straighten", "deskewed": "Straighten", "prepared": "Clarity"}


def _angle(transform: Any) -> float | None:
    extra = getattr(transform, "model_extra", None) or {}
    try:
        return float(extra["angle"])
    except (KeyError, TypeError, ValueError):
        return None


def figure(role: str, transform: Any, note: str | None) -> str:
    """The row's figure in words, from the rendition's `transform` and `note`."""
    angle = _angle(transform)
    if role == "squared":
        return "squared from its corners"
    if role == "flattened":
        return "flattened toward the gutter"
    if role == "rotated" and angle is not None:
        return f"turned {abs(angle):g}° from its text"
    if role == "deskewed" and angle is not None:
        return f"straightened {abs(angle):.1f}°"
    if role == "prepared":
        return "contrast raised"
    if role == "crop":
        method = (getattr(transform, "model_extra", None) or {}).get("method")
        return f"cut to the paper, found by the {method} finder" if method else "cut to the paper"
    return note or role


def image_chain(db: Any, doc: Any) -> dict[str, Any]:
    """The chain for one page, as `ImageChain` serves it."""
    from fichero_server.media.current_image import ORIGINAL, RENDITION, current_page_image, passed_over_renditions
    from fichero_server.media.rendition_order import order_renditions
    from fichero_server.models import Rendition

    root = Path(db.path).parent
    current = current_page_image(db, doc, library_root=root)
    read_from = current.kind if current is not None else ORIGINAL
    read_path = Path(current.path).resolve() if current is not None and current.kind == RENDITION else None
    rows = [r for r in db.query(Rendition, document_id=doc.id) if r.role not in {"original", "thumbnail", "pdf_page_render",
                                                                                "region-crop", "segment-picture"}]
    passed = {row.id: why for row, why in passed_over_renditions(db, doc, library_root=root)}

    def resolved(row: Any) -> Path:
        path = Path(row.path)
        return (path if path.is_absolute() else root / path).resolve()

    def rank(role: str) -> int:
        return _MADE_ORDER.index(role) if role in _MADE_ORDER else len(_MADE_ORDER)

    steps: list[dict[str, Any]] = [{
        "kind": "photograph", "rendition_id": None, "role": "original", "operation": "As it came in",
        "figure": "the photograph", "note": None, "reads_this": read_from == ORIGINAL, "passed_over": None,
        "derived_from": None, "pixel_width": None, "pixel_height": None}]
    for row in sorted(rows, key=lambda r: (r.created_at, rank(r.role), r.id)):
        steps.append({
            "kind": "rendition", "rendition_id": row.id, "role": row.role, "operation": _OPERATION.get(row.role, row.role),
            "figure": figure(row.role, row.transform, row.note), "note": row.note,
            "reads_this": read_path is not None and resolved(row) == read_path, "passed_over": passed.get(row.id),
            "derived_from": row.derived_from_rendition_id, "pixel_width": row.pixel_width, "pixel_height": row.pixel_height})
    return {"page_id": doc.id, "read_from": read_from, "why": current.why if current is not None else "no image file here",
            "steps": steps,
            "passed_over": [{"rendition_id": s["rendition_id"], "role": s["role"], "why": s["passed_over"]}
                            for s in steps if s["passed_over"]],
            "axis": [r.id for r in order_renditions(db.query(Rendition, document_id=doc.id))]}
