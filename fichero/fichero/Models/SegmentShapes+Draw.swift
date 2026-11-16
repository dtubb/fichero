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

    /// The four corners of a normalised `[x, y, width, height]` rect, clockwise from the top left: a marquee
    /// promoted to a region on a segment pass is drawn as this polygon (#6426).
    static func corners(ofRect rect: [Double]) -> [[Double]] {
        guard rect.count >= 4 else { return [] }
        return [[rect[0], rect[1]], [rect[0] + rect[2], rect[1]],
                [rect[0] + rect[2], rect[1] + rect[3]], [rect[0], rect[1] + rect[3]]]
    }

    /// Where Add Region sends marquees: on a page shown from a segment pass, the whole set is drawn as
    /// polygon segments on that pass; one marquee promoted on its own, or any other page, keeps the
    /// regions-artifact route (#6426).
    static func drawsMarqueesOnPass(passShown: Bool, onlyIndex: Int?) -> Bool {
        passShown && onlyIndex == nil
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
    /// A Marker stroke (`segment-editor.marker`): simplified by the engine on the way in, 0 to 1.
    var smoothing: Double?
    /// A Marker baseline: the engine draws the line's outline from the ink.
    var outlineFromBaseline: Bool?
    /// A Paintbrush stroke, `[x, y, width in image pixels]` per point (`segment-editor.paintbrush`).
    var brushStroke: [[Double]]?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", passId = "pass_id", kind, anchor, baseline
        case parentSegmentId = "parent_segment_id", smoothing, outlineFromBaseline = "outline_from_baseline"
        case brushStroke = "brush_stroke"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(documentId, forKey: .documentId)
        try container.encode(passId, forKey: .passId)
        try container.encode(kind, forKey: .kind)
        try container.encode(anchor, forKey: .anchor)
        try container.encodeIfPresent(baseline, forKey: .baseline)
        try container.encodeIfPresent(parentSegmentId, forKey: .parentSegmentId)
        try container.encodeIfPresent(smoothing, forKey: .smoothing)
        try container.encodeIfPresent(outlineFromBaseline, forKey: .outlineFromBaseline)
        try container.encodeIfPresent(brushStroke, forKey: .brushStroke)
    }
}

/// The Marker (`segment-editor.marker`): a freehand stroke that ends near where it began is a closed outline, of the
/// kind last drawn; any other is a baseline, a line whose outline the engine draws from the ink. The engine simplifies
/// either on the way in, so the record never holds a point per pixel.
enum MarkerStroke {
    /// How near the end must come to the start, in screen points, for the stroke to close.
    static let closeWithin = 12.0
    /// The smoothing sent until the tool's popover sets one (not built yet).
    static let smoothing = 0.5

    /// Whether `stroke` (page fractions) ends within `closeWithin` points of its start, on a page drawn `size` big
    /// showing `visible` of the image.
    static func isClosed(_ stroke: [[Double]], size: CGSize, visible: CGRect) -> Bool {
        guard stroke.count >= 3, let first = stroke.first, let last = stroke.last,
              visible.width > 0, visible.height > 0 else { return false }
        let across = (last[0] - first[0]) / visible.width * size.width
        let down = (last[1] - first[1]) / visible.height * size.height
        return (across * across + down * down).squareRoot() <= closeWithin
    }

    /// The one `segment.create` for a finished stroke: closed, a segment of `closedKind` outlined by it; open, a line on
    /// it as a baseline, in `parentSegmentId`'s region. Refused with too few points.
    static func create(
        _ stroke: [[Double]], closed: Bool, closedKind: String, on target: StrokeTarget
    ) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        let (documentId, passId, onPass, parentSegmentId) = (
            target.documentId, target.passId, target.onPass, target.parentSegmentId
        )
        guard stroke.count >= (closed ? 3 : 2), stroke.allSatisfy({ $0.count >= 2 }) else { return .failure(.tooFew) }
        let anchor = SegmentCreateAnchor(
            documentId: documentId, pageId: onPass?.anchor.pageId, renditionId: onPass?.anchor.renditionId,
            space: onPass?.anchor.space, rect: closed ? SegmentShapes.bounds(stroke) : nil, polygon: closed ? stroke : nil,
            shapes: closed ? nil : [SegmentCreateShape(kind: "path", points: stroke)]
        )
        var request = SegmentCreateRequest(
            documentId: documentId, passId: passId, kind: closed ? closedKind : "line", anchor: anchor,
            baseline: closed ? nil : stroke, parentSegmentId: closed ? nil : parentSegmentId
        )
        request.smoothing = smoothing
        request.outlineFromBaseline = closed ? nil : true
        return .success(SegmentEdit.Call(action: "segment.create", params: .create(request)))
    }
}

/// Where a drawn stroke lands: the page, the pass, a segment already on that pass (whose anchor it shares) and
/// the region a line goes in.
struct StrokeTarget {
    let documentId: String
    let passId: String
    var onPass: Segment?
    var parentSegmentId: String?
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

/// The Paintbrush (`segment-editor.paintbrush`): a stroke painted along a line of ink becomes one line, the engine making
/// the painted area its outline and the path its baseline.
enum PaintbrushStroke {
    /// The brush's width on screen (points) as image pixels, for a page drawn `viewWidth` points wide showing `visible`
    /// of an image `imageWidth` pixels wide.
    static func pixels(_ points: Double, viewWidth: Double, visibleWidth: Double, imageWidth: Double) -> Double {
        guard viewWidth > 0 else { return points }
        return points / viewWidth * visibleWidth * imageWidth
    }

    /// The one `segment.create`: a line on the stroke, every point carrying the brush's width, in `parentSegmentId`'s
    /// region. Refused with fewer than two points.
    static func create(
        _ stroke: [[Double]], widthPixels: Double, on target: StrokeTarget
    ) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        let (documentId, passId, onPass, parentSegmentId) = (
            target.documentId, target.passId, target.onPass, target.parentSegmentId
        )
        guard stroke.count >= 2, widthPixels > 0, stroke.allSatisfy({ $0.count >= 2 }) else { return .failure(.tooFew) }
        let anchor = SegmentCreateAnchor(
            documentId: documentId, pageId: onPass?.anchor.pageId, renditionId: onPass?.anchor.renditionId,
            space: onPass?.anchor.space, shapes: [SegmentCreateShape(kind: "path", points: stroke)]
        )
        var request = SegmentCreateRequest(
            documentId: documentId, passId: passId, kind: "line", anchor: anchor, baseline: nil, parentSegmentId: parentSegmentId
        )
        request.brushStroke = stroke.map { [$0[0], $0[1], widthPixels] }
        return .success(SegmentEdit.Call(action: "segment.create", params: .create(request)))
    }
}
