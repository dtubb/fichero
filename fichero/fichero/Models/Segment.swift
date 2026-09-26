import FicheroAPIClient
import Foundation

// MARK: - Segment (source-model App slice A, #4954)

/// One shape on a page — the app's own copy of the contract's `AnchorShape`
/// (source-model slice 7, #4925; carried into the app by #5050).
///
/// A plain struct rather than `Components.Schemas.AnchorShape` for the reason
/// every other value type here exists: views never touch `Components.Schemas.*`,
/// so a generated-type change cannot reach a view without passing through one
/// mapping that a test can pin.
struct AnchorShapeValue: Codable, Hashable {
    /// Which shape this is. **The generated enum, deliberately — #5058.**
    ///
    /// This was a raw `String` on the argument that the engine's kind list is
    /// open by design. **That was wrong, and it conflated two different
    /// lists.** `AnchorShapeKind`'s own contract description says: "A closed
    /// set, like `AnchorSpace` and unlike `granularity`: each kind carries
    /// different data and is validated by its own rule, so a new one is a
    /// change to every reader rather than a label that grows additively."
    ///
    /// The open list is `Segment.kind` / `granularity` — a WORD for what a
    /// region is ("marginalia"), where a project may invent its own and a
    /// reader that does not know it can still draw the box. A shape kind is not
    /// a label: it decides WHICH FIELDS MEAN ANYTHING. A `time` shape carries
    /// `tStart`/`tEnd` and no points; a `point` carries exactly one. A reader
    /// that met a sixth kind would not know what its numbers were, so a new one
    /// genuinely is a change to every reader, exactly as the contract says.
    ///
    /// The `String` was also worse than merely inert. `AnchorShapeKind` is
    /// generated `@frozen` with no unknown case, so an unrecognised kind throws
    /// inside the DECODER before this type is ever constructed — the app could
    /// never have carried one. And the failure is not one shape being declined:
    /// the whole response fails to decode, so a page with one unknown shape
    /// shows nothing at all. The type read as permissive and total while the
    /// layer beneath it was neither, which is what AGENTS.md's totality rule
    /// (ad0ed705d) forbids. `theDecoderRefusesAnUnknownShapeKind` pins that
    /// behaviour so nobody has to rediscover it.
    ///
    /// If this vocabulary should ever be open, that change belongs in the
    /// CONTRACT first — a string here has the downsides of both and the
    /// benefits of neither.
    var kind: Components.Schemas.AnchorShapeKind
    /// Normalized points on the anchor's own image. A `polygon` closes (three
    /// or more), a `path` is open (two or more), a `point` is exactly one, and
    /// a `time` shape carries none at all.
    var points: [[Double]]?
    /// Seconds into `SourceAnchorValue.mediaRef`, for a `time` shape only.
    var tStart: Double?
    var tEnd: Double?

    init(generated: Components.Schemas.AnchorShape) {
        self.kind = generated.kind
        self.points = generated.points
        self.tStart = generated.tStart
        self.tEnd = generated.tEnd
    }
}

/// Where a segment sits on a page image — the app's own copy of the ONE
/// shared anchor (`source.builds-on-the-anchor`), mapped from the generated
/// OUTPUT shape (`SourceAnchor` is generated as two types, input and output;
/// a read-only seam only ever sees the output one). Mirrors `OCRGeometryBox`'s
/// own shape: a plain, Codable, view-facing struct — views never touch
/// `Components.Schemas.*` directly.
struct SourceAnchorValue: Codable, Hashable {
    var documentId: String
    var pageId: String?
    /// WHICH pixel frame `rect` is a fraction of; `nil` means the segment's
    /// own document image. The frame gate (`geometryFrameMatchesDisplay`)
    /// reads this exactly as it reads `OCRGeometry.renditionId` today.
    var renditionId: String?
    /// `"normalized"` or `"pixel"` — kept as the raw string, like
    /// `OCRGeometryBox.level`, so the app never depends on the generated enum.
    var space: String?
    /// Normalized `[x, y, width, height]`, 0…1, top-left origin. `nil` for a
    /// segment whose box could not be held (a degenerate rect, an
    /// out-of-frame polygon…) — `source_model/segments.py::_build_anchor`
    /// drops whatever cannot validate rather than inventing it, and the
    /// reason travels in the owning `Segment.metadata["geometry_problem"]`.
    /// **A `nil` rect must never be drawn, and never given an invented one.**
    var rect: [Double]?
    var polygon: [[Double]]?
    /// A text angle, in degrees. Not read by this slice's draw model (today's
    /// `OCRGeometryBox` carries no rotation) — carried for a later slice.
    var rotation: Double?
    var charStart: Int?
    var charEnd: Int?
    /// The anchor's granularity word (region, line, word, …) — same field
    /// `Segment.kind` below is copied from, at the box's own level.
    var granularity: String?

    // MARK: Slice 7's shapes and slice 8's lasting references (#5050)
    //
    // CARRIED, not drawn by every surface yet. See this type's `init` for the
    // reasoning, which was reversed deliberately and is worth reading before
    // anyone removes a field that looks unused.

    /// Every shape this anchor names, when it names more than a rectangle: a
    /// point, an open path, a polygon, several at once, or a stretch of a
    /// recording (`source.segment.shape-kinds`).
    ///
    /// `nil` means the anchor means what it has always meant — `rect`, or
    /// `polygon`. When shapes ARE present, `rect` is the engine-computed bound
    /// of the area ones, so a surface that only draws rectangles still draws in
    /// the right place; a `point` deliberately leaves `rect` unset, and a
    /// `time` shape has no box at all.
    var shapes: [AnchorShapeValue]?
    /// The recording a `time` shape belongs to.
    var mediaRef: String?
    /// The segment this anchor points AT, recorded rather than recovered
    /// (source-model slice 8, #4932). When set, the engine's `resolve_anchor`
    /// answers from it outright and reports basis `segment-named` — a recorded
    /// fact beats a rectangle matched after the event, and it is the only thing
    /// that works for a segment that never came from a converted artifact.
    var segmentId: String?
    /// The exact reading a `charStart`/`charEnd` span was measured on
    /// (`source.reading.stretch-names-its-reading`). Offsets without this mean
    /// nothing once a line has a second reading.
    var representationId: String?

    /// Deliberately dropped, not silently: `refines` (a recursive anchor
    /// pointing at another anchor — annotations-on-a-region uses this;
    /// `segment_from_box` never sets it for a segment) and the anchor's own
    /// `additionalProperties` (the model's `extra="allow"` catch-all —
    /// `Segment.metadata` below is where a box's own unrecognised data
    /// already travels in this slice; carrying the ANCHOR's separately would
    /// be a second place to look for the same kind of thing).
    ///
    /// **`shapes` and `media_ref` ARE carried, and this reverses an earlier
    /// decision — #5050.** They were dropped in slice 7 on the argument that
    /// this draw model cannot draw them: every surface it feeds renders a
    /// rectangle, the engine already fills `rect` with the bound of the area
    /// shapes, and carrying a field nothing reads is how a second, staler
    /// answer to "what shape is this" gets started.
    ///
    /// That reasoning was right about RENDERERS and wrong about a TYPE, and the
    /// distinction is the whole ruling: **a faithful type is foundation; a
    /// renderer is UI.** While this struct said a segment is a rectangle, every
    /// surface built on it inherited a subset view of reality and would have
    /// had to widen the model before it could do anything — a cost paid by
    /// whoever came next, which is not the mapper's cost to impose. The type is
    /// now total over what the contract DECLARES, and totality is proved by a
    /// round-trip test per field rather than by a renderer existing.
    ///
    /// So these fields being carried is NOT a promise that something draws
    /// them. `regionRect` still prefers the resolved rect exactly as before, and
    /// the polygon overlay is its own work. **Do not delete a field here for
    /// looking unused** — unused is the expected state of a faithful type
    /// between the contract gaining a field and a surface reading it.
    ///
    /// `segment_id` and `representation_id` (slice 8, #4932) are carried for
    /// the same reason, and matter sooner: they are how a mark, a claim or a
    /// stretch says WHICH segment or reading it points at, instead of being
    /// re-derived from a rectangle that may since have moved.
    ///
    /// Every one of these is exercised by the contract-coverage guards in
    /// `SegmentMappingTests`, which fail if `SourceAnchor-Output` gains a
    /// field neither this list nor the mapping below accounts for.
    init(generated: Components.Schemas.SourceAnchorOutput) {
        self.documentId = generated.documentId
        self.pageId = generated.pageId
        self.renditionId = generated.renditionId
        self.space = generated.space?.rawValue
        self.rect = generated.rect
        self.polygon = generated.polygon
        self.rotation = generated.rotation
        self.charStart = generated.charStart
        self.charEnd = generated.charEnd
        self.granularity = generated.granularity
        self.shapes = generated.shapes?.map(AnchorShapeValue.init(generated:))
        self.mediaRef = generated.mediaRef
        self.segmentId = generated.segmentId
        self.representationId = generated.representationId
    }
}

/// One segment, read either from today's `Artifact.ocr_geometry` blob or
/// (once slice 3 lands) a real `Segment` row — the app cannot tell which,
/// and must not try to (`source.one-store`).
struct Segment: Codable, Hashable, Identifiable {
    var id: String
    /// A `legacy:`-prefixed id read from today's blob, never accepted back
    /// on a write path (`source.seam.provisional-ids-refused`). Carried but
    /// shown nowhere in this slice — no visual change.
    var provisional: Bool
    var documentId: String
    var passId: String
    /// The anchor's granularity word (region, line, word, …).
    var kind: String
    /// The producing tool's own label for `kind`, when it differs
    /// (`source.segment.open-kinds`). `nil` until a tool records one.
    var kindRaw: String?
    /// Who made THIS segment — `.human` when the BOX ITSELF proves a person
    /// drew it (the engine's own `_box_is_hand_drawn`, not re-derived here),
    /// else the owning pass's kind. **A segment is hand-drawn exactly when
    /// `provenanceKind == .human`** — the app's whole replacement for
    /// `OCRGeometryBox.isHandDrawn`'s two-signal check; see
    /// `isHandCurated` below.
    var provenanceKind: Components.Schemas.ProvenanceKind
    var anchor: SourceAnchorValue
    /// Normalized `[[x, y], …]` on the same image as `anchor.rect`, only
    /// when the source box actually carried one (never invented).
    var baseline: [[Double]]?
    var text: String?
    var confidence: Double?
    var sourceArtifactId: String?
    /// Position inside the owning artifact's `ocr_geometry.boxes` — only
    /// meaningful, and only ever set, for a provisional segment. Segments
    /// are ordered by this so index-based selection (`RegionSelection`)
    /// keeps meaning the same box after the switch.
    var boxIndex: Int?
    /// Which page of a multi-page PDF this box belongs to (slice 1b,
    /// 77aa741c3). Mapped, not yet READ: `SegmentDisplay` still sets
    /// `pageIndex: nil` on every box it produces — using this to filter a
    /// PDF page's boxes (mirroring `PDFPageWithToolbar.boxesForDisplayedPage`)
    /// is stage 2's job, once the overlays are actually wired to the seam.
    var pageIndex: Int?
    /// Raw pixel values a tool supplied (`raw_polygon_px`, `raw_baseline_px`,
    /// `raw_pixel_frame`) and `geometry_problem` when the anchor could not
    /// hold this box's shape — never interpreted by the draw model, only
    /// carried (`source`: "nothing unrecognised is thrown away").
    var metadata: [String: AnyCodable]?

    /// A segment a PERSON drew, rather than a pass measuring one — the
    /// app's one read of the rule the engine already applied
    /// (`_box_is_hand_drawn`, mirroring `OCRGeometryBox.isHandDrawn`'s own
    /// OR of `provider`/`source`). The app never re-derives the OR itself;
    /// it only asks the engine's own answer.
    var isHandCurated: Bool { provenanceKind == .human }
}

/// One pass, read either from today's blob (one per artifact) or (later) a
/// real `Pass` row.
///
/// Named `…Value` for the same reason `SourceAnchorValue` above is: the
/// obvious name is taken by a GENERATED type. `Components.Schemas.SegmentPass`
/// is the segment-pass ROW, answered by `POST /api/segments/passes`; what
/// this maps from is `Components.Schemas.PassRead`, the seam's read shape.
/// Two different things, and a manual type shadowing a generated name is
/// what `scripts/check_openapi_shadow_types.py` exists to stop -- it is the
/// shape that let a hand-written decoder drift from the wire unnoticed
/// (2026-08-23).
struct SegmentPassValue: Codable, Hashable, Identifiable {
    var id: String
    var provisional: Bool
    var documentId: String
    /// The artifact type this pass came from ("text_geometry",
    /// "transcription", …) — `PassRead.artifactType`, NOT `.name` (`.name`
    /// doubled as the type string before `artifactType` existed; keeping
    /// both mapped, `name` for a later display label, `artifactType` for
    /// ranking).
    var name: String
    var provenanceKind: Components.Schemas.ProvenanceKind
    var provider: String?
    var model: String?
    var runId: String?
    var createdAt: Date?
    /// The pass's own result text (slice 1b, 77aa741c3) — character spans on
    /// a box index into THIS, not into a text rebuilt by joining box texts.
    /// Mapped, not yet READ: `SegmentDisplay` still builds `OCRGeometry.text`
    /// by joining box texts, which `ZoomableImagePreviewMac+EventHandlers`'
    /// `geometryRange(of:)` needs corrected to use this instead — stage 2.
    var text: String?
    var sourceArtifactId: String?
    var artifactType: String?
}

// MARK: - Generated-client mapping

extension Segment {
    /// Map the generated read shape into the app model. Every field of
    /// `Components.Schemas.SegmentRead` is mapped here or is one of the two
    /// this type deliberately has no place for — see `metadata`'s own doc
    /// comment for what is dropped and why. `SegmentMappingCoverageTests`
    /// fails when the generated type's own field set grows past what this
    /// function and `SourceAnchorValue.init(generated:)` account for.
    init(generated: Components.Schemas.SegmentRead) {
        self.id = generated.id
        self.provisional = generated.provisional
        self.documentId = generated.documentId
        self.passId = generated.passId
        self.kind = generated.kind
        self.kindRaw = generated.kindRaw
        self.provenanceKind = generated.provenanceKind
        self.anchor = SourceAnchorValue(generated: generated.anchor)
        self.baseline = generated.baseline
        self.text = generated.text
        self.confidence = generated.confidence
        self.sourceArtifactId = generated.sourceArtifactId
        self.boxIndex = generated.boxIndex
        self.pageIndex = generated.pageIndex
        // Same conversion `ArtifactService.convertToArtifact` already uses
        // for `Artifact.data` — one idiom for "a generated additionalProperties
        // bag becomes `[String: AnyCodable]`", not a second one.
        if let generatedMetadata = generated.metadata {
            var dict: [String: AnyCodable] = [:]
            for (key, value) in generatedMetadata.additionalProperties.value {
                if let unwrapped = value {
                    dict[key] = AnyCodable(unwrapped)
                }
            }
            self.metadata = dict.isEmpty ? nil : dict
        } else {
            self.metadata = nil
        }
    }
}

extension SegmentPassValue {
    /// Map the generated read shape into the app model. Every field of
    /// `Components.Schemas.PassRead` is mapped; none is dropped.
    init(generated: Components.Schemas.PassRead) {
        self.id = generated.id
        self.provisional = generated.provisional
        self.documentId = generated.documentId
        self.name = generated.name
        self.provenanceKind = generated.provenanceKind
        self.provider = generated.provider
        self.model = generated.model
        self.runId = generated.runId
        self.createdAt = generated.createdAt
        self.text = generated.text
        self.sourceArtifactId = generated.sourceArtifactId
        self.artifactType = generated.artifactType
    }
}
