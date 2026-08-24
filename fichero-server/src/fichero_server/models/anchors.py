"""The ONE way a record points at a place on a page.

Before this module there were seven bbox fields across six models, in two unit
systems, with three different meanings and the shared invariant enforced on
exactly one of them (2026-08-20 bbox review):

    Document.bbox              tuple[int x4]  PIXELS   node's region in parent
    Note.bbox                  tuple[int x4]  PIXELS   image annotation position
    ContentSourceAnchor.bbox   list[float]             anchor
    Annotation.bbox            list[float]    0..1     anchor        <- validated
    SourceSupport.source_bbox  list[float]             anchor
    KnowledgeClaim.source_bbox list[float]             anchor
    EvidentialPlace.bbox       list[float]             GEOGRAPHIC extent

The last one is not an image region at all — it sits beside ``lat``/``lon``/
``geojson`` — and is deliberately NOT folded in here; it was renamed
``geo_bbox`` so the collision cannot bite a future reader or a grep-driven
refactor.

Two types live here, and the difference between them is the whole design:

``NodeRegion``
    WHERE A NODE SITS IN ITS PARENT. A split page's half of the opening, a
    cropped map section. Geometry that belongs to the node itself.

``SourceAnchor``
    WHERE A RECORD POINTS ON A NODE. A highlight, an OCR word box, an entity
    mention, a claim's evidence. Geometry that belongs to the thing pointing.

The rule that keeps them apart: **same frame = rendition, different frame =
node.** Alternative pixels of one page (enhanced, background-removed) are
renditions and share the node's frame, so an anchor is portable across them
for free. Anything with a genuinely different frame is a different node with a
``NodeRegion``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class AnchorSpace(str, Enum):
    """What the numbers in a rect are measured in.

    A closed set on purpose — unlike ``granularity`` below, a new coordinate
    space is a breaking change to every consumer, not an additive label.
    """

    #: Fractions of the frame, 0..1, top-left origin. The default and the only
    #: form that survives a rendition being re-rendered at another resolution.
    normalized = "normalized"
    #: Absolute pixels in the frame. Requires the frame's pixel dimensions to
    #: be known to mean anything.
    pixel = "pixel"


#: Float slack for the frame-edge check. A rect assembled as 1/3 + 2/3 does not
#: sum to exactly 1.0 in binary, and rejecting it would fail a rect that is
#: geometrically perfect.
_EDGE_TOLERANCE = 1e-6


def validate_rect(
    value: list[float] | None, *, space: AnchorSpace = AnchorSpace.normalized
) -> list[float] | None:
    """Enforce the ``[x, y, width, height]`` invariant on a rect.

    This check already existed as ``validate_annotation_bbox`` and was wired to
    ONE of the six image-region fields, which is worse than not having it: the
    rule reads as guaranteed while five fields accepted negatives, values above
    1, wrong lengths and NaN. Every anchor and region now runs it by
    construction, so it cannot be skipped by adding a field.
    """
    if value is None:
        return value
    if len(value) != 4:
        raise ValueError(
            f"rect must have exactly 4 elements [x, y, width, height], got {len(value)}"
        )
    for index, component in enumerate(value):
        # NaN is the only value not equal to itself.
        if component != component or component in (float("inf"), float("-inf")):
            raise ValueError(f"rect[{index}] must be finite, got {component}")
        if space is AnchorSpace.normalized and not 0 <= component <= 1:
            raise ValueError(
                f"rect[{index}] must be in [0, 1] for a normalized rect, got {component}"
            )
        if space is AnchorSpace.pixel and component < 0:
            raise ValueError(f"rect[{index}] must be >= 0 in pixel space, got {component}")
    if value[2] <= 0:
        raise ValueError(f"rect width must be > 0, got {value[2]}")
    if value[3] <= 0:
        raise ValueError(f"rect height must be > 0, got {value[3]}")
    if space is AnchorSpace.normalized:
        # Per-component bounds are not enough: [0.5, 0, 0.9, 1] has every
        # component inside [0, 1] and still runs 40% off the right edge. A
        # normalized rect names a fraction OF a frame, so one that leaves the
        # frame is pointing at a place that does not exist — the same silent
        # wrong-place failure as an unnamed frame, one level in.
        #
        # The tolerance absorbs float drift only. An even split writes
        # 0.5 + 0.5, and a full-page box 0.0 + 1.0; both land exactly on the
        # edge, and neither should be rejected for a bit of binary rounding.
        for index, extent in ((0, value[0] + value[2]), (1, value[1] + value[3])):
            if extent > 1.0 + _EDGE_TOLERANCE:
                axis = "x + width" if index == 0 else "y + height"
                raise ValueError(
                    f"{axis} must not exceed 1 for a normalized rect, got {extent}"
                )
    return value


class RegionConfidence(str, Enum):
    """How much a region's rect is actually worth.

    The Marshall sidecars carry ``"method": "nominal-even-split"`` with the
    note that "the fold was not measured" — a 50/50 guess at where an opening
    divides. That is a different fact from a measured fold, and collapsing them
    would make a guess indistinguishable from a measurement. Same three-way
    honesty ``date_meta`` and ``language_meta`` already use.
    """

    #: Derived from the image — a detected fold, a user-drawn rect.
    measured = "measured"
    #: A plausible default nobody verified (an even split, a full-page box).
    nominal = "nominal"
    #: A person placed or corrected it. Survives re-extraction as curation.
    user = "user"


class NodeRegion(BaseModel):
    """Where this node sits inside its parent's frame.

    Replaces three representations of the same fact: ``Document.bbox`` (pixel
    ints), ``metadata["source_bbox"]`` written by the crop/split routes, and
    the staging sidecar's ``region_on_original``. The field names below are
    taken from that sidecar deliberately — the contract already exists in the
    data, and inventing a fourth spelling of it is how there came to be three.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    #: WHICH pixel frame ``rect`` was measured on. ``None`` means the node's
    #: own original frame, which is what every row written before 2026-08-23
    #: means and is correct for a pure resample.
    #:
    #: RESOLVED 2026-08-23 (Daniel). The audit filed this as an open question:
    #: ``SourceAnchor`` named its rendition and ``NodeRegion`` did not, which
    #: was safe only while "same frame = rendition" held — and `rotate_images`
    #: and `auto_crop_border_images` already broke it.
    #:
    #: The ruling is that frames CHAIN: an image is cut to spreads, then to
    #: pages, then rotated, deskewed, background-removed, enhanced, and only
    #: then are diaries extracted from it. Every step in that chain is a new
    #: frame, and a rect measured somewhere along it is meaningless without
    #: saying WHERE. So a region names the rendition it was measured on, for
    #: the same reason an anchor does.
    #:
    #: Optional, and it must stay optional: the alternative is guessing a
    #: rendition for every existing row, which is the invented-frame defect
    #: this whole program removed.
    rendition_id: str | None = None

    #: ``[x, y, width, height]`` in the PARENT's frame.
    rect: list[float]
    space: AnchorSpace = AnchorSpace.normalized
    confidence: RegionConfidence = RegionConfidence.nominal
    #: How the rect was arrived at, e.g. ``"nominal-even-split"``,
    #: ``"detected-fold"``, ``"user-drawn"``. Free-form so the pipeline can
    #: name new methods without a model bump; ``confidence`` is the field
    #: consumers branch on.
    method: str | None = None
    #: Terse, machine-honest provenance note. Not a place for prose.
    note: str | None = None

    # `mode="after"` because a field validator on `rect` runs in DECLARATION
    # order, before `space` is populated — so a pixel-space rect was checked
    # against the 0..1 rule and rejected. Validating the whole model means the
    # rect is always judged against the space it actually declares.
    @model_validator(mode="after")
    def _check_rect(self) -> NodeRegion:
        validate_rect(self.rect, space=self.space)
        return self


class SourceAnchor(BaseModel):
    """Where a record points on a page — the one anchor type.

    Used by annotations, OCR geometry, entity mentions, claim evidence and
    content representations. One type means one overlay renderer, one hit
    tester, one "scroll to this", and one place to get the coordinate maths
    right.

    ``rendition_id`` is the field whose absence caused the original defect: a
    box carried four numbers and never said which pixel frame they were
    fractions OF, so geometry computed on an enhanced or split rendition was
    drawn over the original spread. It is optional only so existing rows stay
    readable — new writes must set it whenever the frame is not the node's own.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    document_id: str
    page_id: str | None = None
    #: WHICH pixel frame ``rect`` is a fraction of. ``None`` means the node's
    #: own frame, which is correct for every rendition that is a pure resample
    #: and wrong for anything cropped, rotated or deskewed.
    rendition_id: str | None = None

    space: AnchorSpace = AnchorSpace.normalized
    #: ``[x, y, width, height]``. ``None`` for a pure text anchor.
    rect: list[float] | None = None
    #: Closed outline for regions a rectangle cannot express — a footnote that
    #: wraps a column, marginalia running down a slanted margin. Points are
    #: ``[[x, y], ...]`` in the same space as ``rect``. Exports as a W3C
    #: ``SvgSelector``.
    polygon: list[list[float]] | None = None
    #: Degrees clockwise, for a region on a page that was never straight.
    rotation: float = 0.0

    #: Character span within the owning artifact's content string.
    char_start: int | None = None
    char_end: int | None = None

    #: What KIND of region this is, from the documented vocabulary in
    #: ``ANCHOR_GRANULARITIES``. Free-form string rather than an enum for the
    #: same reason ``Annotation.anchor_kind`` is: the vocabulary grows
    #: additively with the UI and must not need a model bump.
    granularity: str | None = None

    #: Nesting: this anchor refines another. A transcript span WITHIN a box
    #: WITHIN a page. Maps directly onto W3C Web Annotation's ``refinedBy``,
    #: which the export currently cannot use because selectors are emitted as
    #: a flat "any of these" list.
    refines: SourceAnchor | None = None

    # See NodeRegion._check_rect — same declaration-order trap, same fix.
    @model_validator(mode="after")
    def _check_rect(self) -> SourceAnchor:
        validate_rect(self.rect, space=self.space)
        if self.polygon is not None:
            if len(self.polygon) < 3:
                raise ValueError(
                    f"polygon needs at least 3 points, got {len(self.polygon)}"
                )
            for index, point in enumerate(self.polygon):
                if len(point) != 2:
                    raise ValueError(
                        f"polygon[{index}] must be [x, y], got {len(point)} values"
                    )
                if self.space is AnchorSpace.normalized and not all(
                    0 <= component <= 1 for component in point
                ):
                    raise ValueError(
                        f"polygon[{index}] must be in [0, 1] for a normalized anchor, got {point}"
                    )
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError(
                    f"char_end ({self.char_end}) must be >= char_start ({self.char_start})"
                )
        return self


SourceAnchor.model_rebuild()


#: The shared granularity vocabulary. Documented rather than enumerated so it
#: can grow with the UI; listed here so every producer reaches for the same
#: word instead of inventing one. Today's producers use only a handful — OCR
#: emits ``word``/``line``, the segmenter emits ``page``, diary extraction
#: emits ``entry`` — and the rest exist so layout work has somewhere to land.
ANCHOR_GRANULARITIES: tuple[str, ...] = (
    "glyph",
    "word",
    "line",
    "paragraph",
    "column",
    "block",
    "figure",
    "table",
    "form_region",
    "marginalia",
    "footnote",
    "header",
    "folio_number",
    "entry",
    "event",
    "page",
    "spread",
    #: The part of a split that no child claimed. Recorded, never discarded —
    #: "nothing is destroyed" applies to the offcuts too.
    "waste",
)
