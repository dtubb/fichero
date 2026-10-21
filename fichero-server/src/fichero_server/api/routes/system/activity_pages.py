"""One entry per PAGE of a run, with its state in each stage (`activity.run.page-states`, #5960).

Pure over the job tree `GET /api/activity/jobs/{id}` builds: a page appears once for every step row the lanes handled,
so the step tree has a page many times and the page grid wants it once. The grid reads this, never the step tree.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

#: How a row's own state reads for a page; anything not listed here waits (paused, not run, cancelled, unknown).
_STATE = {
    "done": "done", "completed": "done", "complete": "done", "finished": "done",
    "running": "running", "stopping": "running", "pausing": "running", "resuming": "running", "retrying": "running",
    "failed": "failed", "interrupted": "failed", "quarantined": "failed",
}
#: Several rows for one page read as the first that holds, worst first.
_PRIORITY = ("failed", "running", "waiting", "done")


def _state(raw: Any) -> str:
    return _STATE.get(str(raw or "").lower(), "waiting")


def _worst(states: list[str]) -> str:
    return next(state for state in _PRIORITY if state in states)


def _pages_under(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    if node.get("document_id"):
        yield node
    for child in node.get("children", []):
        yield from _pages_under(child)


def _stage_groups(tree: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(stage id, the node holding that stage's page rows): a recipe run's stage runs by Set Up's stage; any other run is
    one stage, "run"."""
    cards = tree.get("stages")
    if tree.get("kind") != "run-a-recipe" or not cards:
        return [("run", tree)]
    from fichero_server.recipes.stages import stage_of

    by_id = {child["id"]: child for child in tree.get("children", [])}
    groups = []
    for card in cards:
        child = by_id.get(card.get("child_id"))
        if child is None:  # a stage not started: no page rows yet
            continue
        stage = next((s for step in card.get("steps", []) if (s := stage_of(step)) is not None), None)
        groups.append((stage.id if stage else str(card.get("child_id")), child))
    return groups


def page_states(tree: dict[str, Any], stage: Optional[str]) -> list[dict[str, Any]]:
    """The run's pages once each, in the order the lanes first handled them (reading order): `state` and `reason` in the
    asked `stage`, else the worst across stages; `stages` is the state in each.

    ponytail: reading order is the order of first appearance in the tree, which is the lane's order; a run whose first stage
    skipped a page lists it where a later stage first met it."""
    pages: dict[str, dict[str, Any]] = {}
    for stage_id, group in _stage_groups(tree):
        held: dict[str, dict[str, Any]] = {}
        for row in _pages_under(group):
            doc = row["document_id"]
            page = pages.setdefault(doc, {"document_id": doc, "name": row.get("display_name") or doc, "stages": {}})
            cell = held.setdefault(doc, {"states": [], "reasons": []})
            cell["states"].append(_state(row.get("state")))
            if row.get("reason"):
                cell["reasons"].append((_state(row.get("state")), str(row["reason"])))
        for doc, cell in held.items():
            worst = _worst(cell["states"])
            reason = next((text for state, text in cell["reasons"] if state == worst), None)
            page = pages[doc]
            # the same Set Up stage reached by two stage runs keeps its worst
            if stage_id in page["stages"]:
                worst = _worst([page["stages"][stage_id]["state"], worst])
                reason = page["stages"][stage_id]["reason"] or reason
            page["stages"][stage_id] = {"state": worst, "reason": reason}
    out = []
    for page in pages.values():
        cells = page["stages"]
        if stage is not None and stage not in cells:
            continue
        shown = cells[stage] if stage is not None else cells[next(iter(cells))] if len(cells) == 1 else None
        if shown is None:  # no stage asked and several: the worst of them, with its reason
            worst = _worst([cell["state"] for cell in cells.values()])
            shown = next(cell for cell in cells.values() if cell["state"] == worst)
        out.append({"document_id": page["document_id"], "name": page["name"], "state": shown["state"],
                    "reason": shown["reason"], "stages": {sid: cell["state"] for sid, cell in cells.items()}})
    return out
