"""Read ``<file>.renditions.json`` — the staging pipeline's rendition contract.

The engine has been writing these off for months: ``ingest.py`` recognised the
suffix only to avoid importing 450 JSON blobs per diary as documents. The
contract inside is exactly the one the Rendition model was built for, so this
module turns it into rows.

Parsing is separated from applying on purpose. ``plan_renditions`` is pure and
returns a decision — including what it REFUSES to attach and why — so the
refusals are testable and visible rather than being a silent branch inside an
import loop.

The sidecar shape (``fichero-page-renditions-v0-proposed``), from the Marshall
corpus::

    {"schema": ..., "page_external_id": ..., "original_image_stem": ...,
     "part": 1 | null,
     "region_on_original": {"bbox": [x,y,w,h], "space": "page-relative-fraction",
                            "method": "nominal-even-split" | "whole-page",
                            "confidence": "nominal" | "exact", "note": ...},
     "renditions": [{"role", "path", "primary", "note"?, "storage"?,
                     "materialized"?}, ...]}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero_server.models import Rendition
from fichero_server.models.anchors import AnchorSpace, NodeRegion, RegionConfidence

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".renditions.json"
SUPPORTED_SCHEMAS = ("fichero-page-renditions-v0-proposed",)

#: The sidecar's confidence vocabulary mapped onto the model's. ``exact`` is
#: not a fourth enum value: a whole-page region is trivially true rather than
#: detected, and the distinction it carries is already preserved verbatim in
#: ``method`` ("whole-page"), so collapsing it to ``measured`` loses nothing.
_CONFIDENCE_MAP = {
    "nominal": RegionConfidence.nominal,
    "exact": RegionConfidence.measured,
    "measured": RegionConfidence.measured,
    "user": RegionConfidence.user,
}

#: The sidecar spells normalized space this way.
_PAGE_RELATIVE = "page-relative-fraction"


@dataclass
class RenditionPlan:
    """What a sidecar says, resolved against the node it describes."""

    #: Renditions that belong to THIS node — same frame, safe to attach.
    renditions: list[Rendition] = field(default_factory=list)
    #: Where this node sits on its parent, when it is a part of something.
    region_in_parent: NodeRegion | None = None
    #: Entries that describe a DIFFERENT frame and therefore a different node
    #: (a split part's ``original`` is the whole opening). Kept as
    #: ``(role, path, reason)`` so the caller can act or report, never
    #: silently attached to the wrong node — that is the defect this whole
    #: program exists to fix.
    deferred: list[tuple[str, str, str]] = field(default_factory=list)
    #: Non-fatal problems worth surfacing. One malformed sidecar must not fail
    #: a 450-page import whose documents already committed.
    warnings: list[str] = field(default_factory=list)


def sidecar_path_for(source_path: Path) -> Path:
    return source_path.parent / f"{source_path.name}{SIDECAR_SUFFIX}"


def load_sidecar(source_path: Path) -> dict[str, Any] | None:
    """The sidecar beside ``source_path``, or None when there isn't one.

    A malformed sidecar warns and returns None rather than raising: the same
    graceful degradation ``_load_entity_sidecar`` already uses, for the same
    reason — the documents are committed by the time this runs.
    """
    path = sidecar_path_for(source_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("renditions sidecar unreadable at %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("renditions sidecar at %s is not an object", path)
        return None
    return data


def _region_from(raw: dict[str, Any], warnings: list[str]) -> NodeRegion | None:
    rect = raw.get("bbox")
    if not isinstance(rect, list) or len(rect) != 4:
        warnings.append(f"region_on_original.bbox malformed: {rect!r}")
        return None

    space = raw.get("space")
    if space not in (_PAGE_RELATIVE, None):
        # Refuse rather than assume. Guessing at a coordinate space is the
        # original defect in miniature.
        warnings.append(f"unsupported region space {space!r}; region dropped")
        return None

    raw_confidence = str(raw.get("confidence") or "nominal")
    confidence = _CONFIDENCE_MAP.get(raw_confidence)
    note = raw.get("note")
    if confidence is None:
        # An unrecognised confidence becomes the WEAKEST value, never the
        # strongest, and the original word is preserved so nothing is lost.
        # Downgrading silently would still be a lie; downgrading loudly is the
        # honest reading of a vocabulary we do not know.
        confidence = RegionConfidence.nominal
        warnings.append(
            f"unknown confidence {raw_confidence!r} -> nominal (weakest-wins)"
        )
        note = f"[sidecar confidence: {raw_confidence}] {note or ''}".strip()

    try:
        return NodeRegion(
            rect=[float(value) for value in rect],
            space=AnchorSpace.normalized,
            confidence=confidence,
            method=raw.get("method"),
            note=note,
        )
    except (TypeError, ValueError) as exc:
        warnings.append(f"region_on_original rejected: {exc}")
        return None


def plan_renditions(document_id: str, sidecar: dict[str, Any]) -> RenditionPlan:
    """Resolve a sidecar into rows for ``document_id``.

    The one judgement here: a sidecar lists renditions of MORE THAN ONE frame.
    For a whole page (``part`` is null) every entry — including ``original`` —
    is the same frame, so all of them attach. For a split part, ``original`` is
    the whole opening: a different frame and therefore a different node. Those
    are DEFERRED, not attached, because attaching them would reproduce exactly
    the mis-registration this model exists to prevent.

    The rule is read from the data (``part``), not hard-coded per role, so a
    pipeline that starts splitting three ways keeps working.
    """
    plan = RenditionPlan()

    schema = sidecar.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        plan.warnings.append(f"unsupported sidecar schema {schema!r}; skipped")
        return plan

    is_part = sidecar.get("part") is not None

    raw_region = sidecar.get("region_on_original")
    if isinstance(raw_region, dict):
        region = _region_from(raw_region, plan.warnings)
        # A whole page's [0,0,1,1] "region on itself" is not a region in a
        # PARENT — recording it would assert a containment that does not
        # exist. Only a genuine part gets one.
        if region is not None and is_part:
            plan.region_in_parent = region

    entries = sidecar.get("renditions")
    if not isinstance(entries, list):
        plan.warnings.append("renditions[] missing or not a list")
        return plan

    for entry in entries:
        if not isinstance(entry, dict):
            plan.warnings.append(f"rendition entry not an object: {entry!r}")
            continue
        role = str(entry.get("role") or "").strip()
        path = str(entry.get("path") or "").strip()
        if not role or not path:
            plan.warnings.append(f"rendition entry missing role/path: {entry!r}")
            continue

        if is_part and role == "original":
            plan.deferred.append(
                (
                    role,
                    path,
                    "original of a split part is the whole opening — a different "
                    "frame, so it belongs to the parent node, which does not "
                    "exist yet",
                )
            )
            continue

        plan.renditions.append(
            Rendition(
                document_id=document_id,
                role=role,
                path=path,
                is_primary=bool(entry.get("primary", False)),
                storage=entry.get("storage"),
                materialized=bool(entry.get("materialized", True)),
                note=entry.get("note"),
            )
        )

    return plan


def opening_of(sidecar: dict[str, Any]) -> tuple[str, str] | None:
    """The opening a split part belongs to, as ``(stem, original_path)``.

    ``None`` when the sidecar does not describe a part — a whole page belongs
    to no opening, and inventing one would assert a containment that does not
    exist.

    The pairing key is ``original_image_stem`` rather than the file path,
    because the two halves of one opening name the SAME stem while their own
    paths differ. Reading the stem from the data is also what lets a pipeline
    that starts splitting three ways keep working without a code change.
    """
    if sidecar.get("part") is None:
        return None
    stem = sidecar.get("original_image_stem")
    if not stem:
        return None
    for entry in sidecar.get("renditions") or []:
        if isinstance(entry, dict) and entry.get("role") == "original":
            path = entry.get("path")
            if path:
                return (str(stem), str(path))
    return None
