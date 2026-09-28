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

    /// `bbox` with handle `index` dragged to `point`, never thinner than `minimum`.
    static func resized(_ bbox: [Double], handle index: Int, to point: [Double], minimum: Double = 0.002) -> [Double] {
        let handle = handles[index]
        var minX = bbox[0], maxX = bbox[0] + bbox[2], minY = bbox[1], maxY = bbox[1] + bbox[3]
        if handle.x == -1 { minX = point[0] } else if handle.x == 1 { maxX = point[0] }
        if handle.y == -1 { minY = point[1] } else if handle.y == 1 { maxY = point[1] }
        return [min(minX, maxX), min(minY, maxY), max(abs(maxX - minX), minimum), max(abs(maxY - minY), minimum)]
    }
}
