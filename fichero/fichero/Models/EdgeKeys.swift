import Foundation

/// ⌥-arrow and ⌃⌥-arrow on the selected boxes (`segment-editor.edges-move-by-key`): the plan, apart from the keys and the
/// edit that sends it. ⌥ moves the edge on the arrow's side in the arrow's direction (the box grows); ⌃⌥ moves that edge
/// the other way (the box shrinks). Boxes are `[x, y, w, h]` in page fractions.
nonisolated enum EdgeKeys {
    enum Side { case left, right, up, down }

    /// Every box with `side`'s edge moved `pixels` image pixels, outward or back, held to the page and to `minimum`. A box
    /// the move would leave thinner than `minimum` is returned as it was; one that meets the page stops there.
    static func plan(
        _ boxes: [[Double]], side: Side, outward: Bool, pixels: Double, imagePixels: [Double], minimum: Double = 0.002
    ) -> [[Double]] {
        guard imagePixels.count >= 2, imagePixels[0] > 0, imagePixels[1] > 0 else { return boxes }
        return boxes.map { box in
            guard box.count >= 4 else { return box }
            var (minX, minY, maxX, maxY) = (box[0], box[1], box[0] + box[2], box[1] + box[3])
            let sign = outward ? 1.0 : -1.0
            switch side {
            case .left: minX = min(max(minX - sign * pixels / imagePixels[0], 0), 1)
            case .right: maxX = min(max(maxX + sign * pixels / imagePixels[0], 0), 1)
            case .up: minY = min(max(minY - sign * pixels / imagePixels[1], 0), 1)
            case .down: maxY = min(max(maxY + sign * pixels / imagePixels[1], 0), 1)
            }
            guard maxX - minX >= minimum, maxY - minY >= minimum else { return box }
            return [minX, minY, maxX - minX, maxY - minY]
        }
    }
}
