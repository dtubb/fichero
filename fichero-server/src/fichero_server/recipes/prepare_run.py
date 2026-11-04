"""The Prepare Images step of a recipe run: the page operations, then the contrast step where the paper answer says so.
Moved out of `runner.py`, which is over a thousand lines (`runner._run_prepare` is this function, imported there).
"""
from __future__ import annotations

from typing import Any


#: The paper answers that switch a step on (`image.enhance.onboarding-step`); "faded" is the clarity operation's gate.
PAPER_STEPS = {"ruled": "ruled-lines", "show-through": "bleed-through"}


def run_paper_steps(db: Any, documents: list[str], run_id: str, paper: list[str] | None,
                    stop: Any = None) -> dict[str, Any]:
    """The steps the paper answers name (ruled: ruled-lines; show-through: bleed-through, method a), run in that order on each
    page's image into one `enhanced` rendition whose `steps` name each. A page that already has one from this card is left."""
    from pathlib import Path

    from PIL import Image

    from fichero_server.media.enhance import STEPS
    from fichero_server.models import Document, NodeRegion, Rendition
    from fichero_server.models.anchors import RegionConfidence
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    names = [PAPER_STEPS[a] for a in PAPER_STEPS if a in (paper or [])]
    account: dict[str, Any] = {"steps": names, "enhanced": 0, "kept": 0, "no_image": 0}
    if not names:
        return account
    library = Path(db.path).parent
    for doc_id in documents:
        if stop is not None and stop():
            break
        try:
            doc = db.get(Document, doc_id)
            path = _resolve_abs_path(doc, str(library)) if doc is not None else None
            if not path or not Path(path).is_file():
                account["no_image"] += 1
                continue
            if any(r.role == "enhanced" and r.producer_tool == "prepare-the-image" and [x.get("step") for x in r.steps or []] == names
                   for r in db.query(Rendition, document_id=doc.id)):
                account["kept"] += 1
                continue
            with Image.open(path) as opened:
                jpeg = opened.format in ("JPEG", "MPO")
                exif = opened.getexif()
                image = opened if opened.mode in ("RGB", "L") else opened.convert("RGB")
                image = image.copy()
                recorded = []
                for name in names:
                    spec = STEPS[name]
                    image, result = spec.run(image, spec.params())
                    recorded.append({"step": name, "params": spec.params().model_dump(),
                                     "card": {"method": result.get("method", name), "model_id": None}})
            relative = Path("files") / "enhanced" / f"{doc.id}-{'-'.join(names)}.{'jpg' if jpeg else 'png'}"
            (library / relative).parent.mkdir(parents=True, exist_ok=True)
            partial = (library / relative).with_suffix(".part")
            image.save(partial, **({"format": "JPEG", "quality": 95} if jpeg else {"format": "PNG"}), exif=exif)
            partial.replace(library / relative)
            db.save(Rendition(document_id=doc.id, role="enhanced", path=str(relative), is_primary=False,
                              pixel_width=image.width, pixel_height=image.height, producer_run_id=run_id,
                              producer_tool="prepare-the-image", steps=recorded,
                              note=f"the paper answers ran {', '.join(names)}",
                              transform=NodeRegion(rect=[0.0, 0.0, 1.0, 1.0], confidence=RegionConfidence.measured, method="enhance")))
            account["enhanced"] += 1
        except Exception as exc:  # noqa: BLE001 -- one page that fails is skipped and said; the others still go on
            import logging

            logging.getLogger(__name__).warning("paper steps: %s skipped: %s", doc_id, exc)
            account["failed"] = account.get("failed", 0) + 1
    return account


def run_prepare(db: Any, documents: list[str], parent: str,
                 step: dict[str, Any], paper: list[str] | None = None,
                 operations: list[str] | None = None) -> tuple[str | None, str, str | None]:
    """Each faded page gets a prepared rendition (`source.onboard.auto.prepare-damaged-images`, #5580); the step's
    account (`prepared`) says how many it prepared, how many were clear and how many had no image to look at."""
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.runner import _stop_asked
    from fichero_server.recipes import prepare_operations
    from fichero_server.recipes.prepare import prepare_pages

    # The operations the plan chose run, and only those (`wide.prepare.plan-runs-only-chosen-operations`); a card from before
    # the operations existed carries none and runs as it did: the page operations, and the contrast step where the paper
    # answer allows it (`prep.setup.what-runs-by-itself`).
    ops = list(operations) if operations is not None else prepare_operations.to_run(None, paper)
    page_ops = [o for o in ops if o in (prepare_operations.CROP, prepare_operations.STRAIGHTEN)]
    if page_ops:  # find the page, square, flatten, mark blanks (crop); turn, straighten (straighten): the account says what each did
        step["page_prep"] = crop_pages(db, documents, parent, stop=lambda: _stop_asked(parent), prepare=True, reuse=True,
                                       operations=page_ops, signature={"operations": sorted(page_ops)})  # only what changes THESE operations
    if prepare_operations.CLARITY in ops:  # raises only the faded pages: it looks at each and leaves the clear ones
        step["prepared"] = prepare_pages(db, documents, parent, stop=lambda: _stop_asked(parent))
    if "show-through" in (paper or []):  # a page that is only the one before seen through (`image.enhance.show-through-only-verso`)
        from fichero_server.media import show_through_only

        order = {i: n for n, i in enumerate(db.unit_of_work_ids())}
        step["show_through_only"] = show_through_only.mark_pages(
            db, sorted(documents, key=lambda i: order.get(i, len(order))), stop=lambda: _stop_asked(parent))
    if PAPER_STEPS.keys() & set(paper or []):  # ruled paper, writing that shows through (`image.enhance.onboarding-step`)
        step["paper_steps"] = run_paper_steps(db, documents, parent, paper, stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):  # stopped before its next page (#5609): the account counts the pages it looked at
        return None, "cancelled", "Stopped by you"
    return None, "done", None
