"""The re-anchor pass — bbox program step 4 (rulings 2026-08-20).

The root defect this program removes: a box never said which pixel frame its
fractions describe. Steps 1–3 made NEW writes frame-aware. This pass deals
with what already exists: renditions that CLAIM the node's frame
(``transform is None``) while their pixels visibly disagree with it — the
Marshall mis-registration, where boxes measured on the original were drawn
over a cropped/deskewed "enhanced" pass.

The ruling is honesty over guessing: recover the frame from evidence where
evidence exists, and otherwise mark the rendition ``frame_status="unknown"``
so overlays render UNANCHORED on it instead of drawing boxes on pixels whose
frame is unproven. Inventing a transform would recreate the defect.

Classification per rendition (transform None, non-thumbnail):
- ``frame_true``  — pixel dims match the node's frame (the original
  rendition's dims), or a pure resample (same aspect ratio). Anchors pass
  through; nothing to do.
- ``no_evidence`` — the rendition (or the original) records no pixel dims,
  so divergence cannot even be tested. Counted, not marked: absence of
  evidence of divergence is not evidence of divergence, and dims can be
  backfilled by a later pass that opens the files.
- ``divergent``   — dims exist and the aspect ratio disagrees with the
  node's frame beyond tolerance. The rendition claims frame identity it
  does not have → marked ``frame_status="unknown"``.

Plan/apply are separated so the decision is pure and testable, and so the
pass can run as a REPORT before it writes anything (Marshall is real data).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fichero_server.models import Rendition

logger = logging.getLogger(__name__)

#: Aspect ratios within this relative tolerance are the same frame resampled.
#: 2% absorbs rounding from thumbnailing math; a crop that matters moves the
#: aspect far more than this.
_ASPECT_TOLERANCE = 0.02

#: Roles that never carry anchors and may legitimately change aspect.
_EXEMPT_ROLES = {"thumbnail"}

FRAME_STATUS_KEY = "frame_status"
FRAME_UNKNOWN = "unknown"


@dataclass
class ReanchorPlan:
    """What the pass found, before anything is written."""

    frame_true: int = 0
    no_evidence: int = 0
    already_transformed: int = 0
    already_marked: int = 0
    #: Rendition ids to mark ``frame_status="unknown"``, with the reason.
    to_mark: list[tuple[str, str]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "frame_true": self.frame_true,
            "no_evidence": self.no_evidence,
            "already_transformed": self.already_transformed,
            "already_marked": self.already_marked,
            "to_mark": len(self.to_mark),
        }


def _aspect(width: int | None, height: int | None) -> float | None:
    if not width or not height:
        return None
    return width / height


def _node_frame_aspect(renditions: list[Rendition]) -> float | None:
    """The node's own frame, taken from its ``original`` rendition's dims.

    The original IS the node's frame by definition of the model ("a rendition
    never changes what the page is"). Without an original with dims there is
    no reference to test against.
    """
    for rendition in renditions:
        if rendition.role == "original":
            return _aspect(rendition.pixel_width, rendition.pixel_height)
    return None


def classify_rendition(
    rendition: Rendition, node_aspect: float | None
) -> tuple[str, str]:
    """(bucket, reason) for one rendition against its node's frame."""
    if rendition.role in _EXEMPT_ROLES:
        return "frame_true", "exempt role"
    if rendition.transform is not None:
        return "already_transformed", "transform recorded"
    if getattr(rendition, FRAME_STATUS_KEY, None) == FRAME_UNKNOWN:
        return "already_marked", "already marked unknown"
    own = _aspect(rendition.pixel_width, rendition.pixel_height)
    if own is None or node_aspect is None:
        return "no_evidence", "pixel dims absent"
    if abs(own - node_aspect) / node_aspect <= _ASPECT_TOLERANCE:
        return "frame_true", "aspect matches node frame"
    return (
        "divergent",
        f"aspect {own:.4f} vs node {node_aspect:.4f} with no transform recorded",
    )


def plan_reanchor(db) -> ReanchorPlan:
    """Read-only pass over every document that has renditions."""
    plan = ReanchorPlan()
    renditions: list[Rendition] = db.query(Rendition)
    by_doc: dict[str, list[Rendition]] = {}
    for rendition in renditions:
        by_doc.setdefault(rendition.document_id, []).append(rendition)

    for doc_id, doc_renditions in by_doc.items():
        node_aspect = _node_frame_aspect(doc_renditions)
        for rendition in doc_renditions:
            if rendition.role == "original":
                plan.frame_true += 1
                continue
            bucket, reason = classify_rendition(rendition, node_aspect)
            if bucket == "divergent":
                plan.to_mark.append((rendition.id, reason))
            elif bucket == "frame_true":
                plan.frame_true += 1
            elif bucket == "no_evidence":
                plan.no_evidence += 1
            elif bucket == "already_transformed":
                plan.already_transformed += 1
            elif bucket == "already_marked":
                plan.already_marked += 1
        # doc_id is only for logging granularity; keep the loop honest.
        _ = doc_id
    return plan


def apply_reanchor(db, plan: ReanchorPlan) -> int:
    """Mark every planned rendition ``frame_status="unknown"``. Idempotent —
    a marked rendition classifies as ``already_marked`` on the next plan.
    Returns how many rows were written."""
    written = 0
    for rendition_id, reason in plan.to_mark:
        rendition = db.get(Rendition, rendition_id)
        if rendition is None:
            continue
        setattr(rendition, FRAME_STATUS_KEY, FRAME_UNKNOWN)
        # Terse provenance on the row itself, per the model's note contract.
        rendition.note = (
            f"{rendition.note + ' · ' if rendition.note else ''}"
            f"frame unproven ({reason})"
        )
        db.save(rendition)
        written += 1
    if written:
        logger.info("reanchor: marked %d rendition(s) frame-unknown", written)
    return written
