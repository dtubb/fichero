"""The Prepare Images step of a recipe run: the page operations, then the contrast step where the paper answer says so.
Moved out of `runner.py`, which is over a thousand lines (`runner._run_prepare` is this function, imported there).
"""
from __future__ import annotations

from typing import Any


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
                                       operations=page_ops, signature={"paper": sorted(paper or []), "operations": sorted(ops)})
    if prepare_operations.CLARITY in ops:  # raises only the faded pages: it looks at each and leaves the clear ones
        step["prepared"] = prepare_pages(db, documents, parent, stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):  # stopped before its next page (#5609): the account counts the pages it looked at
        return None, "cancelled", "Stopped by you"
    return None, "done", None
