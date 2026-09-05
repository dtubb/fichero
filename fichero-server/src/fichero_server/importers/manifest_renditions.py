"""Turn a manifest node's ``images[]`` into real ``Rendition`` rows.

The manifest importer speaks HTTP and there is no rendition write route — so
until now every corpus import left its image variants as a metadata blob under
``document.metadata["images"]``. That is enough to pick one path to display and
nothing else: the reader cannot swipe between renditions, no row records which
tool made which pass, and a crop's geometry has nowhere to live.

This module closes that gap at the one place a manifest import already holds
the database: the drop path, which stamps paths and dates for the same reason.

The parse/apply split mirrors ``rendition_sidecar.py`` on purpose. ``plan_renditions``
is pure and returns rows *plus* what it refused and why, so the refusals are
testable rather than being a silent branch inside an import loop.

The ``images[]`` contract it reads (all fields but ``role`` optional)::

    {"role": "enhanced", "source_path": "/…/page-1.jpg",
     "derived_from_role": "rotated",          # lineage — frames CHAIN
     "transform": {"rect": [...], "space": ..., "confidence": ..., "method": ...},
     "pixel_width": 3107, "pixel_height": 4734,
     "producer_tool": "fichero-1.0/enhanced", "producer_model": "…"}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import NodeRegion

logger = logging.getLogger(__name__)


@dataclass
class RenditionPlan:
    """What ``plan_renditions`` decided, including what it would not do."""

    renditions: list[Rendition] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)


def plan_renditions(document: Document) -> RenditionPlan:
    """Build the ``Rendition`` rows a document's manifest images describe.

    Pure: builds rows in memory, resolves ``derived_from_role`` to real row
    ids, and refuses anything it cannot honestly represent.
    """
    plan = RenditionPlan()
    images = (document.metadata or {}).get("images") or []
    if not isinstance(images, list):
        plan.refused.append("metadata['images'] is not a list")
        return plan

    by_role: dict[str, Rendition] = {}
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            plan.refused.append(f"images[{index}] is not an object")
            continue
        role = str(image.get("role") or "").strip()
        path = image.get("source_path") or image.get("path")
        if not role:
            plan.refused.append(f"images[{index}] has no role")
            continue
        if not path:
            plan.refused.append(f"{role}: no source_path")
            continue
        if role in by_role:
            # Two rows for one role would make "which one is the enhanced
            # pass?" ambiguous, and the reader picks by role.
            plan.refused.append(f"{role}: duplicate role, keeping the first")
            continue

        transform: NodeRegion | None = None
        raw_transform = image.get("transform")
        if raw_transform:
            try:
                transform = NodeRegion.model_validate(raw_transform)
            except Exception as exc:  # pydantic validation is the contract
                # A bad rect must not cost us the rendition ROW — the pixels
                # are still real, only their geometry is unusable.
                plan.refused.append(f"{role}: transform rejected ({exc})")

        rendition = Rendition(
            document_id=document.id,
            role=role,
            path=str(path),
            pixel_width=_positive_int(image.get("pixel_width")),
            pixel_height=_positive_int(image.get("pixel_height")),
            transform=transform,
            producer_tool=_text(image.get("producer_tool")),
            producer_model=_text(image.get("producer_model")),
            produced_from=str(path),
            storage=_text(image.get("storage")) or "external",
            materialized=True,
            note=_text(image.get("note")),
        )
        by_role[role] = rendition
        plan.renditions.append(rendition)

    # Second pass: lineage, now that every row has an id. Frames chain, so a
    # rendition points at the one it was actually derived from rather than all
    # of them hanging off the original.
    for image in images:
        if not isinstance(image, dict):
            continue
        role = str(image.get("role") or "").strip()
        parent_role = str(image.get("derived_from_role") or "").strip()
        rendition = by_role.get(role)
        if rendition is None or not parent_role:
            continue
        parent = by_role.get(parent_role)
        if parent is None:
            plan.refused.append(f"{role}: derived_from_role '{parent_role}' not present")
            continue
        rendition.derived_from_rendition_id = parent.id
        if rendition.transform is not None and rendition.transform.rendition_id is None:
            # A region is meaningless without naming the frame it was measured
            # on (models/anchors.py) — and that frame is the parent rendition.
            rendition.transform.rendition_id = parent.id

    return plan


def attach_renditions(documents: list[Document], db: Any) -> tuple[int, list[str]]:
    """Write rendition rows for documents that do not have them yet.

    Idempotent by ``(document_id, role)``: re-dropping a corpus repairs missing
    rows instead of stacking duplicates.
    """
    created = 0
    refusals: list[str] = []
    for document in documents:
        if document.doc_type not in ("page", "file"):
            continue
        plan = plan_renditions(document)
        if not plan.renditions:
            refusals.extend(f"{document.id}: {why}" for why in plan.refused)
            continue
        try:
            existing = {
                rendition.role
                for rendition in db.query(Rendition, document_id=document.id)
            }
        except Exception:
            existing = set()
        for rendition in plan.renditions:
            if rendition.role in existing:
                continue
            db.save(rendition)
            created += 1
        refusals.extend(f"{document.id}: {why}" for why in plan.refused)
    if refusals:
        logger.warning(
            "manifest renditions: %d refusal(s), first few: %s",
            len(refusals),
            refusals[:5],
        )
    return created, refusals


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
