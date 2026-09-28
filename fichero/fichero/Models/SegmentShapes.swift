import FicheroAPIClient
import Foundation

/// A segment drawn as ITSELF, not its box (`source.segment.shape-kinds`, `curved-baseline`): the
/// polygon its file drew, an open path, a point, the baseline under the ink -- and Reshape, which
/// moves, adds and removes their points (`source.editor.reshape`) through `segment.update`, checked
/// against the version read, ⌘Z by its audit id. Pure: the rules live where a test can reach them.
/// Every point is normalized `[x, y]`, 0…1, top-left origin, like the box.
enum SegmentShapes {
    /// One thing to draw. The anchor's own extra shapes carry their index in `anchor.shapes`, so a
    /// reshape knows which one it rewrites.
    enum Drawn: Hashable {
        /// The segment's outline: the anchor's polygon.
        case polygon([[Double]])
        /// The line the ink sits on.
        case baseline([[Double]])
        /// A closed `polygon` shape among the anchor's shapes.
        case area([[Double]], shape: Int)
        /// An open `path` shape.
        case path([[Double]], shape: Int)
        /// A `point` shape.
        case point([Double], shape: Int)

        var points: [[Double]] {
            switch self {
            case .polygon(let points), .baseline(let points), .area(let points, _), .path(let points, _): points
            case .point(let point, _): [point]
            }
        }

        /// What reshaping it edits.
        var target: Target {
            switch self {
            case .polygon: .polygon
            case .baseline: .baseline
            case .area(_, let index): .shape(index, .area)
            case .path(_, let index): .shape(index, .path)
            case .point(_, let index): .shape(index, .point)
            }
        }
    }

    /// The kinds of the anchor's extra shapes that are drawn on an image.
    enum ShapeKind: Equatable { case area, path, point }

    /// What Reshape edits: the outline, the baseline, or one of the anchor's extra shapes.
    enum Target: Equatable {
        case polygon
        case baseline
        case shape(Int, ShapeKind)

        /// A closed shape: its last side runs back to its first point.
        var isClosed: Bool {
            switch self {
            case .polygon, .shape(_, .area): true
            default: false
            }
        }

        /// Fewer points than this is not the shape any more: an outline needs three, a line two.
        var minimumPoints: Int {
            switch self {
            case .polygon, .shape(_, .area): 3
            case .baseline, .shape(_, .path): 2
            case .shape(_, .point): 1
            }
        }

        /// How many sides new points can be added on: none for a point.
        func sides(of points: [[Double]]) -> Int {
            if case .shape(_, .point) = self { return 0 }
            return isClosed ? points.count : max(points.count - 1, 0)
        }
    }

    /// Everything a segment draws as, in drawing order: outline(s) first, the baseline over them.
    /// Empty for a segment with nothing but its box (the box is drawn then), and for an unstated shape.
    static func drawn(for segment: Segment) -> [Drawn] {
        guard !segment.shapeIsUnstated else { return [] }
        var out: [Drawn] = []
        if let polygon = usable(segment.anchor.polygon, atLeast: 3) { out.append(.polygon(polygon)) }
        out += (segment.anchor.shapes ?? []).enumerated().compactMap { drawn(for: $1, index: $0) }
        if let baseline = usable(segment.baseline, atLeast: 2) { out.append(.baseline(baseline)) }
        return out
    }

    /// One of the anchor's extra shapes as drawn, or nil: a rect is the box (drawn anyway), and a
    /// stretch of time has no place on an image.
    static func drawn(for shape: AnchorShapeValue, index: Int) -> Drawn? {
        switch shape.kind {
        case .polygon: usable(shape.points, atLeast: 3).map { .area($0, shape: index) }
        case .path: usable(shape.points, atLeast: 2).map { .path($0, shape: index) }
        case .point: usable(shape.points, atLeast: 1)?.first.map { .point($0, shape: index) }
        case .rect, .time: nil
        }
    }

    /// The points Reshape edits for `target`, or nil when the segment has none to edit.
    static func points(of segment: Segment, _ target: Target) -> [[Double]]? {
        switch target {
        case .polygon: usable(segment.anchor.polygon, atLeast: 3)
        case .baseline: usable(segment.baseline, atLeast: 2)
        case .shape:
            drawn(for: segment).first { $0.target == target }?.points
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
        for shape in shapes {
            if let index = shape.points.firstIndex(where: near) { return .vertex(shape.target, index) }
        }
        for shape in shapes {
            if let index = sideMidpoints(shape.points, shape.target).firstIndex(where: near) {
                return .side(shape.target, index)
            }
        }
        return nil
    }

    /// One point of one shape of one box: what the arrow keys nudge in Edit Segments.
    struct PointRef: Equatable {
        let documentId: String
        let boxIndex: Int
        let target: Target
        let index: Int
    }

    /// One point moved by whole image PIXELS (an arrow key: 1, with ⇧ 10), on an image `imageSize`
    /// pixels across, clamped to the page.
    static func nudging(_ points: [[Double]], index: Int, byPixels delta: [Double], imageSize: [Double]) -> [[Double]] {
        guard points.indices.contains(index), delta.count >= 2, imageSize.count >= 2,
              imageSize[0] > 0, imageSize[1] > 0 else { return points }
        let point = points[index]
        return moving(points, index: index, to: [point[0] + delta[0] / imageSize[0], point[1] + delta[1] / imageSize[1]])
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
        guard (0..<target.sides(of: points)).contains(index), point.count >= 2 else { return points }
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
        (0..<target.sides(of: points)).map { index in
            let start = points[index], end = points[(index + 1) % points.count]
            return [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
        }
    }

    /// The edit to send: the baseline alone, or the anchor rewritten with the outline or the one extra
    /// shape changed -- carrying every other shape unchanged, so none is dropped -- and a rect only when
    /// the shapes enclose an area (a flat line has none to state). Refused, and said, when the version
    /// read is unknown or the shape would have too few points.
    static func reshape(
        _ segment: Segment, _ target: Target, to points: [[Double]]
    ) -> Result<SegmentEdit.Call, SegmentEdit.Refusal> {
        guard let version = segment.version else { return .failure(.versionUnknown) }
        guard points.count >= target.minimumPoints, points.allSatisfy({ $0.count >= 2 }) else {
            return .failure(.tooFew)
        }
        if target == .baseline {
            return .success(SegmentEdit.Call(
                action: "segment.update",
                params: .baseline(SegmentBaselineRequest(segmentId: segment.id, expectedVersion: version, baseline: points))
            ))
        }
        let polygon = target == .polygon ? points : segment.anchor.polygon
        let shapes = segment.anchor.shapes.map { shapes in
            shapes.enumerated().map { index, shape in
                AnchorShapeParams(
                    kind: shape.kind.rawValue, points: target == .shape(index, kindOf(shape)) ? points : shape.points,
                    tStart: shape.tStart, tEnd: shape.tEnd
                )
            }
        }
        let spatial = (polygon ?? []) + (shapes ?? []).filter { $0.kind != "time" }.flatMap { $0.points ?? [] }
        let box = bounds(spatial)
        let anchor = SegmentAnchorParams(
            documentId: segment.anchor.documentId, pageId: segment.anchor.pageId,
            renditionId: segment.anchor.renditionId, space: segment.anchor.space,
            rect: box[2] > 0 && box[3] > 0 ? box : nil, polygon: polygon,
            rotation: segment.anchor.rotation, granularity: segment.anchor.granularity, shapes: shapes
        )
        return .success(SegmentEdit.Call(
            action: "segment.update",
            params: .update(SegmentUpdateRequest(segmentId: segment.id, expectedVersion: version, anchor: anchor))
        ))
    }

    /// An anchor shape's kind as a reshape target names it (a rect or time shape is never one).
    private static func kindOf(_ shape: AnchorShapeValue) -> ShapeKind {
        switch shape.kind {
        case .polygon: .area
        case .point: .point
        default: .path
        }
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

/// One of the anchor's shapes, as a rewrite sends it back: every field it had.
struct AnchorShapeParams: Encodable, Equatable {
    let kind: String
    let points: [[Double]]?
    let tStart: Double?
    let tEnd: Double?

    enum CodingKeys: String, CodingKey {
        case kind, points, tStart = "t_start", tEnd = "t_end"
    }
}

/// A Reshape in progress (`source.editor.reshape`): which box, what is reshaped, the point being
/// dragged, and the points as they stand -- committed on release as one `segment.update`.
struct ReshapeDrag: Equatable {
    let boxIndex: Int
    let target: SegmentShapes.Target
    let pointIndex: Int
    var points: [[Double]]
    /// The points before the press, so a press that moves nothing sends nothing.
    let original: [[Double]]

    /// What a press in Edit Segments does to the ONE selected box: nothing (no handle under it), removes
    /// a point (⌥ on a point), refuses (⌥ on a point the shape cannot spare), or begins a drag -- of the
    /// point pressed, or of a new point on the side pressed. The image overlay and a PDF page both ask
    /// here, so the two surfaces reshape by one rule. `reach` is a handle's size on screen, normalized.
    enum Press: Equatable {
        case none
        case remove(SegmentShapes.Target, [[Double]])
        case refused
        case drag(ReshapeDrag)
    }

    static func press(
        at point: [Double], boxIndex: Int, shapes: [SegmentShapes.Drawn], reach: [Double], option: Bool
    ) -> Press {
        guard let handle = SegmentShapes.handle(at: point, in: shapes, tolerance: reach),
              let points = shapes.first(where: { $0.target == handle.target })?.points else { return .none }
        switch handle {
        case .vertex(let target, let vertex) where option:
            guard let fewer = SegmentShapes.removing(points, index: vertex, target) else { return .refused }
            return .remove(target, fewer)
        case .vertex(let target, let vertex):
            return .drag(ReshapeDrag(boxIndex: boxIndex, target: target, pointIndex: vertex, points: points, original: points))
        case .side(let target, let after):
            let added = SegmentShapes.adding(points, after: after, at: point, target)
            return .drag(ReshapeDrag(boxIndex: boxIndex, target: target, pointIndex: after + 1, points: added, original: points))
        }
    }
}
