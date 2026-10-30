"""What the Prepare Images actions share with the edit routes: the request models of the square, blank and contrast rows,
and the small helpers that read and answer a page's proposals. A leaf module (it imports nothing from the routes), so
`image_editing` and `image_prepare_actions` can both use it without a cycle.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext
from fichero_server.db import Database


class ContrastOperationRequest(BaseModel):
    """`factor` is the old PIL contrast; any of the rest makes it the CLAHE step (`image.enhance.contrast-clahe`)."""

    factor: float = Field(1.0, ge=0.0, le=10.0)
    clip: float | None = Field(None, ge=1.0, le=4.0)
    tile: int | None = Field(None, ge=4, le=16)
    gain: float | None = Field(None, ge=0.8, le=1.4)
    lift: float | None = Field(None, ge=-20.0, le=20.0)
    profile: Literal["handwritten", "typescript"] | None = None
    page: int = Field(1, ge=1)


class SquareOperationRequest(BaseModel):
    """The page's four corners, top-left clockwise, in fractions of the upright image (`prep.square.*`)."""

    # [x, y] pairs as lists, not tuples: a tuple makes a prefixItems schema the generated Swift client cannot type
    quad: list[Annotated[list[float], Field(min_length=2, max_length=2)]] = Field(min_length=4, max_length=4)
    page: int = Field(1, ge=1)


class MarkBlankOperationRequest(BaseModel):
    """A page marked blank (hidden, skipped) or not blank (`prep.check.blank-mark-is-a-correction`)."""

    blank: bool
    page: int = Field(1, ge=1)


def _proposal_state(doc: Any) -> dict[str, Any]:
    meta = doc.metadata or {}
    return {"proposals": dict(meta.get("prep_proposals") or {}), "answered": dict(meta.get("prep_answered") or {})}


def _invert_proposals(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    if not before or not before.get("document_id"):
        return None
    return "image.restore_proposals", {
        "document_id": before["document_id"], "proposals": before.get("proposals", {}),
        "answered": before.get("answered", {}), "operations": before.get("operations")}


def _answer_proposal(db: Database, doc: Any, kind: str) -> None:
    """A person answered the run's proposal of `kind`: it leaves the worklist and the run does not propose it again."""
    meta = dict(doc.metadata or {})
    meta["prep_proposals"] = {k: v for k, v in (meta.get("prep_proposals") or {}).items() if k != kind}
    meta["prep_answered"] = {**(meta.get("prep_answered") or {}), kind: "person"}
    doc.metadata = meta
    db.save(doc)
