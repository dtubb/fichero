"""Mapping rects between a node's frame and its parent's.

This is the arithmetic that makes ``NodeRegion`` more than a record. A split
page knows where it sits on the opening; a box drawn on the page can therefore
be shown on the opening, and a box found on the opening can be shown on the
page. Without it the geometry is stored honestly and still cannot answer the
question anyone actually asks.

Everything here is pure and normalized-only. Pixel-space rects must be
converted by their owner first, using the frame's pixel dimensions — mixing
the two silently is the original defect in miniature, so it raises instead.

Confidence propagates by WEAKEST-WINS: composing a measured region through a
nominal one yields nominal. A chain is only as trustworthy as its shakiest
link, and a result that inherited "measured" from one step would misreport the
whole. Same reasoning as ``date_meta`` refusing to let a precise day survive
an imprecise range.
"""

from __future__ import annotations

from fichero_server.models.anchors import (
    AnchorSpace,
    NodeRegion,
    RegionConfidence,
    validate_rect,
)

#: Weakest-wins ordering. ``user`` outranks ``measured`` because a person who
#: corrected a rect has overruled the detector on purpose, and that decision
#: must survive re-extraction (the same rule ``date_meta["source"] == "user"``
#: already follows).
_CONFIDENCE_RANK: dict[RegionConfidence, int] = {
    RegionConfidence.nominal: 0,
    RegionConfidence.measured: 1,
    RegionConfidence.user: 2,
}


def _require_normalized(region: NodeRegion, what: str) -> None:
    if region.space is not AnchorSpace.normalized:
        raise ValueError(
            f"{what} must be in normalized space to compose, got {region.space.value}. "
            "Convert with the frame's pixel dimensions first — mixing spaces "
            "silently is exactly the bug this module exists to prevent."
        )


def weakest_confidence(*regions: NodeRegion) -> RegionConfidence:
    """The least trustworthy confidence among ``regions``."""
    if not regions:
        return RegionConfidence.nominal
    return min(regions, key=lambda r: _CONFIDENCE_RANK[r.confidence]).confidence


def rect_to_parent(rect: list[float], region: NodeRegion) -> list[float]:
    """Express ``rect`` — given in the NODE's frame — in the PARENT's frame.

    The node occupies ``region.rect`` of its parent, so a fraction of the node
    is that same fraction of the region, offset to where the region starts.

        parent_x = region.x + rect.x * region.width

    A full-page rect ``[0, 0, 1, 1]`` therefore maps exactly onto the region
    itself, which is the property worth remembering: the node's whole frame IS
    its region in the parent.
    """
    _require_normalized(region, "region")
    validate_rect(rect)
    origin_x, origin_y, width, height = region.rect
    return [
        origin_x + rect[0] * width,
        origin_y + rect[1] * height,
        rect[2] * width,
        rect[3] * height,
    ]


def rect_from_parent(rect: list[float], region: NodeRegion) -> list[float] | None:
    """Express ``rect`` — given in the PARENT's frame — in the NODE's frame.

    The inverse of :func:`rect_to_parent`. Returns ``None`` when ``rect`` does
    not overlap ``region`` at all: the honest answer to "where is this on that
    page?" when it simply is not on that page. Callers must not read ``None``
    as "at the origin".

    A rect that only PARTIALLY overlaps is returned clipped to the node, since
    a line of text crossing a fold really is partly on each half, and losing
    the visible part would be worse than reporting it.
    """
    _require_normalized(region, "region")
    validate_rect(rect)
    origin_x, origin_y, width, height = region.rect

    # Intersect in parent space first, so a non-overlapping rect is rejected
    # before any division makes it look plausible.
    left = max(rect[0], origin_x)
    top = max(rect[1], origin_y)
    right = min(rect[0] + rect[2], origin_x + width)
    bottom = min(rect[1] + rect[3], origin_y + height)
    if right <= left or bottom <= top:
        return None

    return [
        (left - origin_x) / width,
        (top - origin_y) / height,
        (right - left) / width,
        (bottom - top) / height,
    ]


def compose(outer: NodeRegion, inner: NodeRegion) -> NodeRegion:
    """Collapse two hops into one.

    ``inner`` is a region within ``outer``'s frame; ``outer`` is a region
    within its own parent's. The result expresses ``inner`` directly in that
    grandparent frame — the operation that walks a node up an arbitrarily deep
    tree (chunk in page, page in opening, opening in folder) without
    re-deriving anything.

    The composed ``method`` records the hops rather than inventing a new name,
    so provenance survives the collapse instead of being flattened into a
    plausible-looking single step.
    """
    _require_normalized(outer, "outer region")
    _require_normalized(inner, "inner region")
    return NodeRegion(
        rect=rect_to_parent(inner.rect, outer),
        space=AnchorSpace.normalized,
        confidence=weakest_confidence(outer, inner),
        method=_composed_method(outer, inner),
        note=None,
    )


def _composed_method(outer: NodeRegion, inner: NodeRegion) -> str | None:
    parts = [part for part in (outer.method, inner.method) if part]
    if not parts:
        return None
    return " -> ".join(parts)


def compose_chain(regions: list[NodeRegion]) -> NodeRegion | None:
    """Collapse a whole ancestry, outermost FIRST.

    ``[opening_in_folder, page_in_opening, box_in_page]`` yields the box
    expressed in the folder's frame. Empty list returns ``None`` — there is no
    such thing as an identity region, and inventing ``[0, 0, 1, 1]`` would
    claim the node fills its parent, which is a real and different assertion.
    """
    if not regions:
        return None
    result = regions[0]
    for region in regions[1:]:
        result = compose(result, region)
    return result
