import FicheroAPIClient
import Foundation

/// A segment drawn as ITSELF, not its box (`source.segment.shape-kinds`, `curved-baseline`): the
/// polygon its file drew, an open path, a point, the baseline under the ink -- and Reshape, which
/// moves, adds and removes their points (`source.editor.reshape`) through `segment.update`, checked
/// against the version read, ⌘Z by its audit id. Pure: the rules live where a test can reach them.
/// Every point is normalized `[x, y]`, 0…1, top-left origin, like the box.
enum SegmentShapes {
    /// One thing to draw.
    enum Drawn: Hashable {
        /// A closed outline: the anchor's polygon, or an `area` shape.
        case polygon([[Double]])
        /// An open path: a `path` shape.
        case path([[Double]])
        /// One point.
        case point([Double])
        /// The line the ink sits on.
        case baseline([[Double]])

        var points: [[Double]] {
            switch self {
            case .polygon(let points), .path(let points), .baseline(let points): points
            case .point(let point): [point]
            }
        }
    }

    /// What Reshape edits: the outline or the baseline.
    enum Target: Equatable {
        case polygon
        case baseline

        /// Fewer points than this is not the shape any more: a polygon needs three, a line two.
        var minimumPoints: Int { self == .polygon ? 3 : 2 }
    }

    /// Everything a segment draws as, in drawing order: outline(s) first, the baseline over them.
    /// Empty for a segment with nothing but its box (the box is drawn then), and for an unstated shape.
    static func drawn(for segment: Segment) -> [Drawn] {
        guard !segment.shapeIsUnstated else { return [] }
        var out: [Drawn] = []
        if let polygon = usable(segment.anchor.polygon, atLeast: 3) { out.append(.polygon(polygon)) }
        out += (segment.anchor.shapes ?? []).compactMap(drawn(for:))
        if let baseline = usable(segment.baseline, atLeast: 2) { out.append(.baseline(baseline)) }
        return out
    }

    /// One of the anchor's extra shapes as drawn, or nil: a rect is the box (drawn anyway), and a
    /// stretch of time has no place on an image.
    static func drawn(for shape: AnchorShapeValue) -> Drawn? {
        switch shape.kind {
        case .polygon: usable(shape.points, atLeast: 3).map(Drawn.polygon)
        case .path: usable(shape.points, atLeast: 2).map(Drawn.path)
        case .point: usable(shape.points, atLeast: 1)?.first.map(Drawn.point)
        case .rect, .time: nil
        }
    }

    /// The points Reshape edits for `target`, or nil when the segment has none to edit.
    static func points(of segment: Segment, _ target: Target) -> [[Double]]? {
        switch target {
        case .polygon: usable(segment.anchor.polygon, atLeast: 3)
        case .baseline: usable(segment.baseline, atLeast: 2)
        }
    }

    // MARK: - Reshape: move, add, remove

    /// What a press in Edit Segments landed on: a point of the outline or baseline (drag it, or
    /// ⌥-click to remove it), or a side's midpoint (add a point there and drag it).
    enum Handle: Equatable {
        case vertex(Target, Int)
        case side(Target, Int)

        var target: Target {
            switch self {
            case .vertex(let target, _), .side(let target, _): target
            }
        }
    }

    /// The handle under `point`, within `tolerance` (normalized `[dx, dy]`, the handle's reach on
    /// screen at this zoom). A point wins over a side midpoint; the outline's over the baseline's.
    static func handle(at point: [Double], in shapes: [Drawn], tolerance: [Double]) -> Handle? {
        guard point.count >= 2, tolerance.count >= 2 else { return nil }
        let near = { (other: [Double]) in abs(other[0] - point[0]) <= tolerance[0] && abs(other[1] - point[1]) <= tolerance[1] }
        let editable: [(Target, [[Double]])] = shapes.compactMap {
            switch $0 {
            case .polygon(let points): (.polygon, points)
            case .baseline(let points): (.baseline, points)
            case .path, .point: nil
            }
        }
        for (target, points) in editable {
            if let index = points.firstIndex(where: near) { return .vertex(target, index) }
        }
        for (target, points) in editable {
            if let index = sideMidpoints(points, target).firstIndex(where: near) { return .side(target, index) }
        }
        return nil
    }

    /// One point dragged, clamped to the page.
    static func moving(_ points: [[Double]], index: Int, to point: [Double]) -> [[Double]] {
        guard points.indices.contains(index), point.count >= 2 else { return points }
        var out = points
        out[index] = [clamp(point[0]), clamp(point[1])]
        return out
    }

    /// A point added on the side from `index` to the next: a polygon's last side closes to the first,
    /// a baseline has no side after its last point.
    static func adding(_ points: [[Double]], after index: Int, at point: [Double], _ target: Target) -> [[Double]] {
        let sides = target == .polygon ? points.count : points.count - 1
        guard (0..<sides).contains(index), point.count >= 2 else { return points }
        var out = points
        out.insert([clamp(point[0]), clamp(point[1])], at: index + 1)
        return out
    }

    /// A point removed; nil when that would leave fewer than the shape needs (said, never done).
    static func removing(_ points: [[Double]], index: Int, _ target: Target) -> [[Double]]? {
        guard points.indices.contains(index), points.count > target.minimumPoints else { return nil }
        var out = points
        out.remove(at: index)
        return out
    }

    /// The midpoints of each side: where a point can be added.
    static func sideMidpoints(_ points: [[Double]], _ target: Target) -> [[Double]] {
        let sides = target == .polygon ? points.count : max(points.count - 1, 0)
        return (0..<sides).map { index in
            let start = points[index], end = points[(index + 1) % points.count]
            return [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
        }
    }

    /// The edit to send: the polygon as the anchor (with the rect it bounds, as a move sends both), or
    /// the baseline alone. Refused, and said, when the version read is unknown, when the shape would
    /// have too few points, or when the segment has extra shapes an anchor rewrite would drop.
    static func reshape(
        _ segment: Segment, _ target: Target, to points: [[Double]]
    ) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard let version = segment.version else { return .failure(.versionUnknown) }
        guard points.count >= target.minimumPoints, points.allSatisfy({ $0.count >= 2 }) else {
            return .failure(.tooFew)
        }
        switch target {
        case .baseline:
            return .success(SegmentEdit.Call(
                action: "segment.update",
                params: .baseline(SegmentBaselineRequest(segmentId: segment.id, expectedVersion: version, baseline: points))
            ))
        case .polygon:
            guard segment.anchor.shapes?.isEmpty ?? true else { return .failure(.hasExtraShapes) }
            let anchor = SegmentAnchorParams(
                documentId: segment.anchor.documentId, pageId: segment.anchor.pageId,
                renditionId: segment.anchor.renditionId, space: segment.anchor.space, rect: bounds(points),
                polygon: points, rotation: segment.anchor.rotation, granularity: segment.anchor.granularity
            )
            return .success(SegmentEdit.Call(
                action: "segment.update",
                params: .update(SegmentUpdateRequest(segmentId: segment.id, expectedVersion: version, anchor: anchor))
            ))
        }
    }

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
        _ kind: DrawKind, points: [[Double]], documentId: String, passId: String, onPass: Segment?
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
            baseline: polygon ? nil : points
        ))))
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

    /// The box around `points`: `[x, y, w, h]`.
    static func bounds(_ points: [[Double]]) -> [Double] {
        let xValues = points.map { $0[0] }, yValues = points.map { $0[1] }
        let minX = xValues.min() ?? 0, minY = yValues.min() ?? 0
        return [minX, minY, (xValues.max() ?? 0) - minX, (yValues.max() ?? 0) - minY]
    }

    private static func usable(_ points: [[Double]]?, atLeast count: Int) -> [[Double]]? {
        guard let points, points.count >= count, points.allSatisfy({ $0.count >= 2 }) else { return nil }
        return points
    }

    private static func clamp(_ value: Double) -> Double { min(1, max(0, value)) }
}

/// `segment.update` with the baseline alone -- the anchor untouched.
struct SegmentBaselineRequest: Encodable, Equatable {
    let segmentId: String
    let expectedVersion: Int
    let baseline: [[Double]]

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", expectedVersion = "expected_version", baseline
    }
}

/// `segment.create` from the Shape tool: a new segment on the shown pass.
struct SegmentCreateRequest: Encodable, Equatable {
    let documentId: String
    let passId: String
    let kind: String
    let anchor: SegmentCreateAnchor
    let baseline: [[Double]]?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", passId = "pass_id", kind, anchor, baseline
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(documentId, forKey: .documentId)
        try container.encode(passId, forKey: .passId)
        try container.encode(kind, forKey: .kind)
        try container.encode(anchor, forKey: .anchor)
        try container.encodeIfPresent(baseline, forKey: .baseline)
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
