import Foundation

/// Resizing a selected box by its eight handles, as Preview.app does (`source.editor.selection-like-preview`,
/// #5215). The handles are `SelectionStyle.handleRects`' eight, in the same order: the corners and the edge
/// midpoints. A corner moves two edges; an edge midpoint moves one. Dragging past the opposite edge flips
/// the box rather than inverting it. All in normalized page units, `[x, y, w, h]`.
nonisolated enum BoxResize {
    /// A resize under way: the box (its position in the full list), the handle pressed, the box as it is now.
    struct Drag: Equatable {
        let index: Int
        let handle: Int
        var bbox: [Double]
        /// Every box the drag moves (the selection, its first the one pressed) as they were, their positions in the full
        /// list, and as they are now. One box: just that one.
        var indices: [Int] = []
        var origins: [[Double]] = []
        var live: [[Double]] = []
        /// Where the press was, and the one axis ⇧ fixed once the pointer moved past `axisThreshold` (nil until then).
        var start: [Double] = []
        var axis: Axis?
    }

    /// The one axis a ⇧-drag changes (`segment-editor.expand-one-axis`): horizontal moves the left or right edge,
    /// vertical the top or bottom.
    enum Axis { case horizontal, vertical }

    /// How far the pointer must travel before the first direction counts, in page fractions.
    static let axisThreshold = 0.004

    /// The axis of a drag from `start` to `point`: the larger of the two distances once either is past `threshold`; nil before that.
    static func axis(from start: [Double], to point: [Double], threshold: Double = axisThreshold) -> Axis? {
        guard start.count >= 2, point.count >= 2 else { return nil }
        let across = abs(point[0] - start[0]), down = abs(point[1] - start[1])
        guard max(across, down) > threshold else { return nil }
        return across >= down ? .horizontal : .vertical
    }

    /// Which edges each handle moves: -1 the minimum edge, 1 the maximum, 0 neither, on x then y.
    static let handles: [(x: Int, y: Int)] = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    /// Where handle `index` sits on `bbox`.
    static func position(of index: Int, on bbox: [Double]) -> [Double] {
        let handle = handles[index]
        return [bbox[0] + Double(handle.x + 1) / 2 * bbox[2], bbox[1] + Double(handle.y + 1) / 2 * bbox[3]]
    }

    /// The handle under `point`, within `reach` (a handle's size on screen, normalized), or nil.
    static func handle(at point: [Double], of bbox: [Double], reach: [Double]) -> Int? {
        guard bbox.count >= 4, point.count >= 2, reach.count >= 2 else { return nil }
        return handles.indices.first { index in
            let place = position(of: index, on: bbox)
            return abs(place[0] - point[0]) <= reach[0] && abs(place[1] - point[1]) <= reach[1]
        }
    }

    /// `bbox` with handle `index` dragged to `point`, never thinner than `minimum`. With an `axis`, only that axis's edges
    /// move: the other stays where it was.
    static func resized(
        _ bbox: [Double], handle index: Int, to point: [Double], axis: Axis? = nil, minimum: Double = 0.002
    ) -> [Double] {
        var handle = handles[index]
        if axis == .vertical { handle.x = 0 } else if axis == .horizontal { handle.y = 0 }
        var minX = bbox[0], maxX = bbox[0] + bbox[2], minY = bbox[1], maxY = bbox[1] + bbox[3]
        if handle.x == -1 { minX = point[0] } else if handle.x == 1 { maxX = point[0] }
        if handle.y == -1 { minY = point[1] } else if handle.y == 1 { maxY = point[1] }
        return [min(minX, maxX), min(minY, maxY), max(abs(maxX - minX), minimum), max(abs(maxY - minY), minimum)]
    }

    /// What grabbing a handle or edge looks like under the pointer.
    enum Cursor: Equatable { case arrow, leftRight, upDown, diagonal }

    /// The cursor over handle `index` (nil: over no handle or edge): an edge moving along x shows left-right, along y up-down,
    /// a corner the diagonal.
    static func cursor(overHandle index: Int?) -> Cursor {
        guard let index else { return .arrow }
        let handle = handles[index]
        if handle.x != 0, handle.y != 0 { return .diagonal }
        return handle.x != 0 ? .leftRight : .upDown
    }

    /// The handle or edge under `point` (`segment-editor.edges-drag-and-say-so`): a corner within `reach` first, then any
    /// point within `reach` of an edge along its whole length, so a thin line box is grabbed by its edge and not only by a
    /// midpoint handle. Nil inside the box clear of every edge, or outside.
    static func grab(at point: [Double], of bbox: [Double], reach: [Double]) -> Int? {
        guard bbox.count >= 4, point.count >= 2, reach.count >= 2 else { return nil }
        let corners = [0, 2, 5, 7]
        if let corner = corners.first(where: { index in
            let place = position(of: index, on: bbox)
            return abs(place[0] - point[0]) <= reach[0] && abs(place[1] - point[1]) <= reach[1]
        }) { return corner }
        let (minX, maxX, minY, maxY) = (bbox[0], bbox[0] + bbox[2], bbox[1], bbox[1] + bbox[3])
        let withinX = point[0] >= minX - reach[0] && point[0] <= maxX + reach[0]
        let withinY = point[1] >= minY - reach[1] && point[1] <= maxY + reach[1]
        let nearest = [
            (index: 1, gap: abs(point[0] - minX), along: withinY, reachGap: reach[0]),
            (index: 6, gap: abs(point[0] - maxX), along: withinY, reachGap: reach[0]),
            (index: 3, gap: abs(point[1] - minY), along: withinX, reachGap: reach[1]),
            (index: 4, gap: abs(point[1] - maxY), along: withinX, reachGap: reach[1])
        ].filter { $0.along && $0.gap <= $0.reachGap }.min { $0.gap < $1.gap }
        return nearest?.index
    }

    /// Every box in `boxes` with handle `index` moved by `delta` (page fractions): the same edge or corner of each, by the
    /// same amount, none thinner than `minimum`. The several-box edge drag.
    static func resizedTogether(_ boxes: [[Double]], handle index: Int, by delta: [Double], minimum: Double = 0.002) -> [[Double]] {
        boxes.map { box in
            let place = position(of: index, on: box)
            return resized(box, handle: index, to: [place[0] + delta[0], place[1] + delta[1]], minimum: minimum)
        }
    }
}
