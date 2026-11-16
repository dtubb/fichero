"""A page that is only the previous recto seen through the paper (`image.enhance.show-through-only-verso`, #6197).

The leaf rule of Find the Documents applies: a page right after a written page is that page's verso. The verso is show-through-only
when it has no ink of its own (the darkest 0.5 % of its darkness is under `OWN_INK_MAX` of the recto's) and its mirrored, registered
darkness matches the recto's (a correlation of at least `MATCH_MIN`). The mark is document metadata: `page_kind: show-through-only`,
`show_through_of` (the recto), `show_through_score`. Leave Out reads `show_through_only` and leaves every line of the page out
with the page-level reason; nothing is deleted, and the page stays the verso input of bleed-through method b.
"""
from __future__ import annotations

from typing import Any

from PIL import Image

KIND = "show-through-only"
OWN_INK_MAX = 0.5
MATCH_MIN = 0.5
#: The recto must have ink to be seen through.
RECTO_INK_MIN = 40.0


def match(recto: Image.Image, verso: Image.Image) -> dict[str, Any]:
    """`{"show_through_only": bool, "score": correlation or None, "reason": ...}` for a recto and the page after it."""
    try:
        import cv2
        import numpy as np

        from fichero_server.media.enhance import bleed_through as bt
    except ImportError:
        return {"show_through_only": False, "score": None, "reason": "no OpenCV"}
    recto_rgb, verso_rgb = np.asarray(recto.convert("RGB")), np.asarray(verso.convert("RGB"))
    recto_dark = bt._darkness(recto_rgb, bt._paper(recto_rgb, 60))
    verso_dark = bt._darkness(verso_rgb, bt._paper(verso_rgb, 60))
    recto_ink, verso_ink = float(np.percentile(recto_dark, 99.5)), float(np.percentile(verso_dark, 99.5))
    if recto_ink < RECTO_INK_MIN:
        return {"show_through_only": False, "score": None, "reason": "the page before has no ink to see through"}
    if verso_ink > OWN_INK_MAX * recto_ink:
        return {"show_through_only": False, "score": None, "reason": "it has ink of its own"}
    found = bt.register_verso(np.clip(recto_dark, 0, 255).astype("uint8"), np.clip(verso_dark, 0, 255).astype("uint8"))
    if found is None:
        return {"show_through_only": False, "score": None, "reason": "it does not register to the page before"}
    warp, mirrored = found
    height, width = recto_dark.shape
    aligned = cv2.warpAffine(mirrored.astype(np.float32), warp, (width, height),
                             flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0)
    a, b = np.clip(recto_dark, 0, None).ravel(), aligned.ravel()
    score = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
    return {"show_through_only": score >= MATCH_MIN, "score": round(score, 3),
            "reason": "its mirrored marks match the page before" if score >= MATCH_MIN else "its marks do not match the page before"}


def mark_pages(db: Any, ordered_ids: list[str], stop: Any = None) -> dict[str, Any]:
    """Judge each page that follows another in `ordered_ids` (the project's page order) and mark the show-through-only ones.
    A page a person already ruled on (the mark present, or `show_through_checked`) is not judged again."""
    from pathlib import Path

    from fichero_server.models import Document
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    library = str(Path(db.path).parent)
    account: dict[str, Any] = {"marked": 0, "looked_at": 0, "kept": 0, "no_image": 0}
    for previous_id, page_id in zip(ordered_ids, ordered_ids[1:]):
        if stop is not None and stop():
            break
        page = db.get(Document, page_id)
        before = db.get(Document, previous_id)
        if page is None or before is None:
            continue
        meta = dict(page.metadata or {})
        if meta.get("page_kind") == KIND or meta.get("show_through_checked"):
            account["kept"] += 1
            continue
        paths = (_resolve_abs_path(before, library), _resolve_abs_path(page, library))
        if not all(p and Path(p).is_file() for p in paths):
            account["no_image"] += 1
            continue
        with Image.open(paths[0]) as recto, Image.open(paths[1]) as verso:
            result = match(recto, verso)
        account["looked_at"] += 1
        meta["show_through_checked"] = True
        if result["show_through_only"]:
            meta.update({"page_kind": KIND, "show_through_only": True, "show_through_of": previous_id,
                         "show_through_score": result["score"]})
            account["marked"] += 1
        db.save(page.model_copy(update={"metadata": meta}))
    return account


def include(meta: dict[str, Any], included: bool) -> dict[str, Any]:
    """The metadata with the page included in reading (or left out again); the mark stays either way."""
    out = dict(meta or {})
    out["show_through_included"] = bool(included)
    return out


def clear(meta: dict[str, Any]) -> dict[str, Any]:
    """The metadata without the mark (the page is judged again only if `show_through_checked` is dropped by the caller)."""
    return {k: v for k, v in (meta or {}).items()
            if k not in {"page_kind", "show_through_only", "show_through_of", "show_through_score", "show_through_included", "show_through_brought_back"}}
