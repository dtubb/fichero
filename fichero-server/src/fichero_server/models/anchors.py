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

#: Ids minted by a READ SEAM rather than written as records: a box's position
#: in today's `ocr_geometry` blob (`legacy:`) and an artifact's text read as a
#: reading (`legacy-reading:`). Defined HERE, the lowest layer, because both
#: `models/segments.py` (which re-exports them) and `SourceAnchor` below must
#: refuse them, and anchors.py imports nothing from this package.
#: `source.seam.provisional-ids-refused`.
LEGACY_ID_PREFIX = "legacy:"
LEGACY_READING_ID_PREFIX = "legacy-reading:"
PROVISIONAL_ID_PREFIXES = (LEGACY_ID_PREFIX, LEGACY_READING_ID_PREFIX)

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


def validate_points(
    points: list[list[float]] | None,
    *,
    space: AnchorSpace = AnchorSpace.normalized,
    minimum: int = 1,
    exact: int | None = None,
    label: str = "points",
) -> list[list[float]] | None:
    """Enforce the point-list invariant, as ``validate_rect`` does for a rect.

    Slice 7 (#4925): the anchor grows past the rectangle, and the shapes that
    arrive with it -- an open path along a slanted line, a lone point on a
    signature, a polygon around a footnote -- need the SAME checks the rect
    has always had, or the rule would read as guaranteed on one field and be
    absent on four. Every number finite; every point inside the image for a
    normalized anchor; and the count each kind requires.

    The tolerance is ``_EDGE_TOLERANCE``, the one the polygon check already
    uses (#4955): a point assembled as ``1/3 + 2/3`` lands a bit past 1.0 and
    is geometrically perfect.
    """
    if points is None:
        return points
    if exact is not None and len(points) != exact:
        raise ValueError(f"{label} must have exactly {exact} point(s), got {len(points)}")
    if len(points) < minimum:
        raise ValueError(f"{label} needs at least {minimum} point(s), got {len(points)}")
    for index, point in enumerate(points):
        if len(point) != 2:
            raise ValueError(f"{label}[{index}] must be [x, y], got {len(point)} values")
        for component in point:
            # NaN is the only value not equal to itself.
            if component != component or component in (float("inf"), float("-inf")):
                raise ValueError(f"{label}[{index}] must be finite, got {point}")
        if space is AnchorSpace.normalized and not all(
            -_EDGE_TOLERANCE <= component <= 1 + _EDGE_TOLERANCE for component in point
        ):
            raise ValueError(
                f"{label}[{index}] must be in [0, 1] for a normalized anchor, got {point}"
            )
    return points


class AnchorShapeKind(str, Enum):
    """The shapes an anchor may name (slice 7, #4925).

    A closed set, like ``AnchorSpace`` and unlike ``granularity``: each kind
    carries different data and is validated by its own rule, so a new one is a
    change to every reader rather than a label that grows additively.
    """

    #: A rectangle given as its corner points. The same place ``rect`` names,
    #: said in the shapes list so one anchor can hold a rectangle beside a
    #: polygon without either being the odd one out.
    rect = "rect"
    #: A closed outline, three points or more.
    polygon = "polygon"
    #: An OPEN line, two points or more -- a slanted line's run, a rule, a
    #: pen stroke. Closing it would claim an area nobody drew.
    path = "path"
    #: One place, exactly one point. A signature's position, a marginal mark.
    point = "point"
    #: A stretch of a recording, in seconds. Carries no points and no box.
    time = "time"


#: How many points each kind needs. A path of one point is a point that lies
#: about being a line; a polygon of two is a path that lies about enclosing
#: something. Both are refused rather than quietly reinterpreted.
_SHAPE_MINIMUM_POINTS: dict[AnchorShapeKind, int] = {
    # Two opposite corners are enough to mean a rectangle, and four corners
    # mean the same one; the derived box is identical either way, so both are
    # accepted rather than picking a spelling for callers.
    # ponytail: minimum, not exact — the bound does not care how many corners.
    AnchorShapeKind.rect: 2,
    AnchorShapeKind.polygon: 3,
    AnchorShapeKind.path: 2,
    AnchorShapeKind.point: 1,
}

#: The kinds that enclose or trace an AREA of the page, and so have a box.
#: ``time`` is the one that does not: it names a stretch of a recording.
AREA_SHAPE_KINDS: frozenset[AnchorShapeKind] = frozenset(
    {
        AnchorShapeKind.rect,
        AnchorShapeKind.polygon,
        AnchorShapeKind.path,
        AnchorShapeKind.point,
    }
)


class AnchorShape(BaseModel):
    """ONE shape on an anchor (slice 7, #4925).

    An anchor may carry several, which is the point: a line and the marginal
    mark beside it are one place as far as the record is concerned, and before
    this there was no way to say that without inventing a second anchor.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    kind: AnchorShapeKind
    #: ``[[x, y], ...]`` in the anchor's own space. ``None`` only for ``time``.
    points: list[list[float]] | None = None
    #: Seconds into the recording named by the anchor's ``media_ref``.
    t_start: float | None = None
    t_end: float | None = None

    # The space is the ANCHOR's, so the point bounds cannot be checked here.
    # This validator enforces everything that does not need it, and
    # `SourceAnchor._check_rect` re-runs `validate_points` with the space.
    @model_validator(mode="after")
    def _check_shape(self) -> AnchorShape:
        if self.kind is AnchorShapeKind.time:
            if self.points:
                raise ValueError("a time shape carries no points")
            if self.t_start is None or self.t_end is None:
                raise ValueError("a time shape needs t_start and t_end")
            for name, value in (("t_start", self.t_start), ("t_end", self.t_end)):
                if value != value or value in (float("inf"), float("-inf")):
                    raise ValueError(f"{name} must be finite, got {value}")
            if self.t_start < 0:
                raise ValueError(f"t_start must be >= 0, got {self.t_start}")
            if not self.t_start < self.t_end:
                raise ValueError(
                    f"t_start ({self.t_start}) must be < t_end ({self.t_end})"
                )
            return self
        if self.t_start is not None or self.t_end is not None:
            raise ValueError(f"only a time shape carries t_start/t_end, not {self.kind.value}")
        validate_points(
            self.points,
            minimum=_SHAPE_MINIMUM_POINTS[self.kind],
            exact=1 if self.kind is AnchorShapeKind.point else None,
            label=f"{self.kind.value} points",
            # Bounds are re-checked with the anchor's space; here only the
            # shape and count of the list are in scope.
            space=AnchorSpace.pixel,
        )
        if self.points is None:
            raise ValueError(f"a {self.kind.value} shape needs points")
        return self


def shapes_bound(shapes: list[AnchorShape] | None) -> list[float] | None:
    """The box around every AREA shape — the derived box (slice 7, #4925).

    ``None`` when there is nothing with an extent: no shapes, or only time
    spans. A lone point gives a box of zero width and height AT the point:
    honest about where it is and honest that it encloses nothing. That box is
    allowed in ``Segment.bbox_*``, which the engine writes, and never in
    ``SourceAnchor.rect``, which promises a drawable rectangle.
    """
    points = [
        point
        for shape in shapes or ()
        if shape.kind in AREA_SHAPE_KINDS
        for point in shape.points or ()
    ]
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


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
    #: Shapes past the rectangle (slice 7, #4925): a point, an open path, a
    #: polygon, several of them at once, a stretch of a recording. Optional,
    #: so every anchor stored before this slice stays valid and keeps meaning
    #: exactly what it meant -- ``rect``, or ``polygon``. When shapes ARE
    #: present, ``rect`` is the bound of the area ones, worked out below; a
    #: caller that sends a rect disagreeing with them is refused rather than
    #: having one of its two answers silently preferred.
    shapes: list[AnchorShape] | None = None
    #: The recording a ``time`` shape is a stretch OF. The field only:
    #: recordings themselves are a later slice, and a time shape without it
    #: names seconds of nothing, so it is refused.
    media_ref: str | None = None

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

    # ---- Source-model slice 8 (#4932/#4934): the LASTING references --------
    #
    # THE PROBLEM THESE SOLVE. Everything that points at a piece of a source
    # -- a mark, a claim, a support, a reading's stretch -- has until now
    # pointed with a RECTANGLE. Move the line and the pointer stays where the
    # box used to be. `resolve_anchor` can recover the link afterwards, from
    # the kept block, because a rectangle plus an artifact gives a repeatable
    # id -- but recovering a link is not the same as having recorded one, and
    # it only works for a box that came from a converted artifact.
    #
    # So an anchor may now name what it points at OUTRIGHT. One shape for
    # readings, marks, supports and claims, because "where in the source" is
    # ONE question and had accumulated one answer per caller.

    #: The segment this anchor points at. When set it is AUTHORITATIVE and
    #: `resolve_anchor` returns it without matching rectangles at all: a
    #: recorded fact beats a recovered one. Never a provisional (`legacy:`)
    #: id -- that names a position in a blob, so storing one would be a
    #: lasting reference to something that does not last.
    segment_id: str | None = None

    #: The exact reading a character span was measured on
    #: (`source.reading.stretch-names-its-reading`). Offsets without this are
    #: meaningless the moment a second reading of the line exists, and when
    #: the named reading is superseded the stretch is carried over by matching
    #: CHARACTERS (`readings.replace_stretch`) or reported unplaced -- never
    #: re-measured by position alone.
    representation_id: str | None = None

    @model_validator(mode="after")
    def _check_lasting_references(self) -> SourceAnchor:
        """A lasting reference must not be a provisional id (slice 8, #4932).

        Checked ON THE MODEL, not only at the write paths, because an anchor
        travels: it is embedded in claims, annotations, notes and readings, and
        a caller that skipped a route's own check would otherwise store a
        pointer that stops meaning anything the next time the page is re-run.
        Old stored anchors have neither field, so nothing existing is refused.
        """
        for field_name in ("segment_id", "representation_id"):
            value = getattr(self, field_name)
            if value is not None and value.startswith(PROVISIONAL_ID_PREFIXES):
                raise ValueError(
                    f"{field_name} {value!r} is provisional (read from today's "
                    "stored geometry, not a real record) and cannot be stored "
                    "in an anchor"
                )
        return self

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
                # #4955: the SAME `_EDGE_TOLERANCE` `validate_rect` allows past
                # the image edge (float drift only, e.g. 1/3 + 2/3 landing at
                # 1.0000000000000002) -- a polygon point drifting the same way
                # used to drop the WHOLE polygon while the same drift in a
                # rect or a baseline (`segments.py::_COORD_TOLERANCE`) was
                # kept. One tolerance for every edge-of-image check.
                if self.space is AnchorSpace.normalized and not all(
                    -_EDGE_TOLERANCE <= component <= 1 + _EDGE_TOLERANCE
                    for component in point
                ):
                    raise ValueError(
                        f"polygon[{index}] must be in [0, 1] for a normalized anchor, got {point}"
                    )
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError(
                    f"char_end ({self.char_end}) must be >= char_start ({self.char_start})"
                )
        self._check_shapes()
        return self

    def _check_shapes(self) -> None:
        """The shapes' bounds, and the rect they derive (slice 7, #4925).

        Split out only because ``_check_rect`` was already at its length; it
        runs as part of the same single validator, so a shape can no more be
        added past the check than a rect can.
        """
        if self.shapes is None:
            return
        if not self.shapes:
            raise ValueError("shapes must not be empty; leave it unset instead")
        for index, shape in enumerate(self.shapes):
            # Now the space is known, so the bounds are in scope. The counts
            # were already enforced on the shape itself.
            validate_points(
                shape.points,
                space=self.space,
                label=f"shapes[{index}] ({shape.kind.value})",
            )
            if shape.kind is AnchorShapeKind.time and not self.media_ref:
                raise ValueError(
                    f"shapes[{index}] is a time span, so the anchor needs a media_ref"
                )
        bound = shapes_bound(self.shapes)
        if self.rect is not None:
            if bound is None:
                raise ValueError(
                    "rect is set but no shape has an extent; a time-only anchor has no box"
                )
            if any(
                abs(given - derived) > _EDGE_TOLERANCE
                for given, derived in zip(self.rect, bound)
            ):
                raise ValueError(
                    f"rect {self.rect} disagrees with the shapes' bound {bound}; "
                    "the engine derives the rect -- send the shapes, or send a "
                    "rect that matches them"
                )
            return
        # Derive it, so every reader that already knows how to draw a rect can
        # draw the new shapes' extent for free. A DEGENERATE bound -- a lone
        # point, a level path -- is deliberately NOT written here: `rect`
        # promises a drawable rectangle with width and height above zero, and
        # `validate_rect` would refuse it. The box still exists for the engine
        # through `shapes_bound`, which is where `Segment.bbox_*` gets it.
        if bound is not None and bound[2] > 0 and bound[3] > 0:
            self.rect = bound


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
