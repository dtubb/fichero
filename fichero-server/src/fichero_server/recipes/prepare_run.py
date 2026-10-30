"""The Prepare Images step of a recipe run: the page operations, then the contrast step where the paper answer says so.
Moved out of `runner.py`, which is over a thousand lines (`runner._run_prepare` is this function, imported there).
"""
from __future__ import annotations

from typing import Any


def run_prepare(db: Any, documents: list[str], parent: str,
                 step: dict[str, Any], paper: list[str] | None = None) -> tuple[str | None, str, str | None]:
    """Each faded page gets a prepared rendition (`source.onboard.auto.prepare-damaged-images`, #5580); the step's
    account (`prepared`) says how many it prepared, how many were clear and how many had no image to look at."""
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.runner import _stop_asked
    from fichero_server.recipes.prepare import prepare_pages, runs_contrast

    # The Set Up step's operations first, on every page whatever the answers (`prep.setup.what-runs-by-itself`): find the
    # page, square, flatten, turn, straighten, mark blanks; the account (`page_prep`) counts what each did.
    step["page_prep"] = crop_pages(db, documents, parent, stop=lambda: _stop_asked(parent), prepare=True)
    # The contrast step runs where the answer says the paper is faded; with no paper answer it looks at each page and
    # raises only the faded ones (`prep.setup.what-runs-by-itself`).
    if runs_contrast(paper):
        step["prepared"] = prepare_pages(db, documents, parent, stop=lambda: _stop_asked(parent))
    if _stop_asked(parent):  # stopped before its next page (#5609): the account counts the pages it looked at
        return None, "cancelled", "Stopped by you"
    return None, "done", None
