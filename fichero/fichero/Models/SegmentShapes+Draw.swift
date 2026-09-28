import Foundation

/// The Shape tool's polygon and baseline (`source.editor.draw-shapes`), apart from `SegmentShapes`'
/// drawing and reshaping for file_length.
extension SegmentShapes {
    // MARK: - Draw: the Shape tool's polygon and baseline (`source.editor.draw-shapes`)

    /// What the one Shape tool draws. A box is dragged (the band, as it always was); a polygon and a
    /// baseline are clicked point by point.
    enum DrawKind: String, CaseIterable, Identifiable {
        case box, polygon, baseline
        var id: String { rawValue }
        var title: String {
            switch self {
            case .box: "Box"
            case .polygon: "Polygon"
            case .baseline: "Baseline"
            }
        }
        /// Points it needs before it can be finished.
        var minimumPoints: Int { self == .baseline ? 2 : 3 }
    }

    /// A click on the FIRST point of a polygon with enough points closes it.
    static func closes(_ points: [[Double]], at point: [Double], tolerance: [Double]) -> Bool {
        guard points.count >= DrawKind.polygon.minimumPoints, let first = points.first,
              point.count >= 2, tolerance.count >= 2 else { return false }
        return abs(first[0] - point[0]) <= tolerance[0] && abs(first[1] - point[1]) <= tolerance[1]
    }

    /// The segment a finished drawing makes on the shown pass: a polygon is a REGION anchored by its
    /// outline (with the rect it bounds, as a reshape sends); a baseline is a LINE whose anchor is the
    /// baseline itself as an open path -- no outline is invented for it -- and whose `baseline` it is.
    /// The anchor's page, image and space are those of a segment already on the pass (`onPass`), so the
    /// new one names the same picture. Refused, and said, with too few points.
    static func create(
        _ kind: DrawKind, points: [[Double]], documentId: String, passId: String, onPass: Segment?,
        parentSegmentId: String? = nil
    ) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard kind != .box, points.count >= kind.minimumPoints, points.allSatisfy({ $0.count >= 2 }) else {
            return .failure(.tooFew)
        }
        let polygon = kind == .polygon
        let anchor = SegmentCreateAnchor(
            documentId: documentId, pageId: onPass?.anchor.pageId, renditionId: onPass?.anchor.renditionId,
            space: onPass?.anchor.space, rect: polygon ? bounds(points) : nil, polygon: polygon ? points : nil,
            shapes: polygon ? nil : [SegmentCreateShape(kind: "path", points: points)]
        )
        return .success(SegmentEdit.Call(action: "segment.create", params: .create(SegmentCreateRequest(
            documentId: documentId, passId: passId, kind: polygon ? "region" : "line", anchor: anchor,
            baseline: polygon ? nil : points, parentSegmentId: polygon ? nil : parentSegmentId
        ))))
    }

    /// The region a drawn line belongs in: the one that holds MOST of the drawing's bounds -- more than
    /// half, measured by area (a flat baseline padded to `minimumSpan`, as it is drawn) -- never merely
    /// the first one touched. Nil when no region holds most of it: the line stays at page level, and the
    /// path says so. Ties go to the smaller region, the more specific one.
    static func containingRegion(for points: [[Double]], among segments: [Segment], minimumSpan: Double = 0.004) -> Segment? {
        guard !points.isEmpty else { return nil }
        var drawn = bounds(points)
        if drawn[2] < minimumSpan { drawn[0] -= (minimumSpan - drawn[2]) / 2; drawn[2] = minimumSpan }
        if drawn[3] < minimumSpan { drawn[1] -= (minimumSpan - drawn[3]) / 2; drawn[3] = minimumSpan }
        let area = drawn[2] * drawn[3]
        struct Candidate {
            let segment: Segment
            let share: Double
            let size: Double
        }
        let scored: [Candidate] = segments.compactMap { segment in
            guard segment.kind.lowercased() == "region", !segment.provisional,
                  let box = segment.anchor.rect ?? segment.anchor.polygon.map(bounds), box.count >= 4 else { return nil }
            let width = min(drawn[0] + drawn[2], box[0] + box[2]) - max(drawn[0], box[0])
            let height = min(drawn[1] + drawn[3], box[1] + box[3]) - max(drawn[1], box[1])
            guard width > 0, height > 0 else { return nil }
            return Candidate(segment: segment, share: width * height / area, size: box[2] * box[3])
        }
        return scored.filter { $0.share > 0.5 }
            .min { $0.share != $1.share ? $0.share > $1.share : $0.size < $1.size }?.segment
    }

    /// The box a segment is drawn and clicked by when its anchor states none: its shapes' bounds, never
    /// thinner than `minimumSpan` -- a flat baseline must still be clickable. Nil without shapes.
    static func displayBox(for segment: Segment, minimumSpan: Double = 0.004) -> [Double]? {
        let points = drawn(for: segment).flatMap(\.points)
        guard !points.isEmpty else { return nil }
        var box = bounds(points)
        if box[2] < minimumSpan { box[0] -= (minimumSpan - box[2]) / 2; box[2] = minimumSpan }
        if box[3] < minimumSpan { box[1] -= (minimumSpan - box[3]) / 2; box[3] = minimumSpan }
        return box
    }
}

/// `segment.create` from the Shape tool: a new segment on the shown pass.
struct SegmentCreateRequest: Encodable, Equatable {
    let documentId: String
    let passId: String
    let kind: String
    let anchor: SegmentCreateAnchor
    let baseline: [[Double]]?
    /// The region a drawn line is drawn inside (`SegmentShapes.containingRegion`); nil at page level.
    var parentSegmentId: String?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", passId = "pass_id", kind, anchor, baseline
        case parentSegmentId = "parent_segment_id"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(documentId, forKey: .documentId)
        try container.encode(passId, forKey: .passId)
        try container.encode(kind, forKey: .kind)
        try container.encode(anchor, forKey: .anchor)
        try container.encodeIfPresent(baseline, forKey: .baseline)
        try container.encodeIfPresent(parentSegmentId, forKey: .parentSegmentId)
    }
}

/// A drawn segment's anchor: only what the drawing states, the rest absent (never null-as-a-claim).
struct SegmentCreateAnchor: Encodable, Equatable {
    let documentId: String
    var pageId: String?
    var renditionId: String?
    var space: String?
    var rect: [Double]?
    var polygon: [[Double]]?
    var shapes: [SegmentCreateShape]?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", pageId = "page_id", renditionId = "rendition_id", space, rect, polygon, shapes
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(documentId, forKey: .documentId)
        try container.encodeIfPresent(pageId, forKey: .pageId)
        try container.encodeIfPresent(renditionId, forKey: .renditionId)
        try container.encodeIfPresent(space, forKey: .space)
        try container.encodeIfPresent(rect, forKey: .rect)
        try container.encodeIfPresent(polygon, forKey: .polygon)
        try container.encodeIfPresent(shapes, forKey: .shapes)
    }
}

struct SegmentCreateShape: Encodable, Equatable {
    let kind: String
    let points: [[Double]]
}
