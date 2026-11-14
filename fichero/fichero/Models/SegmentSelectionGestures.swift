import Foundation

/// The selection gestures on the page in Select (`segment-editor.select-marquee-lasso`, `segment-editor.select-shift-toggles`),
/// as pure rules so they are tested as decisions. Points are the page's fractions.
enum SegmentSelectionGestures {
    /// One box on the page: its index in the full list, its `[x, y, w, h]`, its level (`OCRGeometryBox.level`).
    struct Box {
        let index: Int
        let bbox: [Double]
        let level: String
    }

    /// The level a band or lasso selects: regions when ⌘ is held as it starts, else lines when the page shows any, else
    /// whatever is shown (nil).
    static func level(of boxes: [Box], commandHeld: Bool) -> String? {
        if commandHeld { return "region" }
        return boxes.contains { $0.level == "line" } ? "line" : nil
    }

    /// The boxes at `level` (nil: any) whose area is MOSTLY (over half) inside the drawn `loop`, a closed polygon; a band
    /// is the loop of its four corners.
    static func inside(_ loop: [[Double]], boxes: [Box], level: String?) -> [Int] {
        guard loop.count >= 3 else { return [] }
        return boxes.filter { box in
            (level == nil || box.level == level) && shareInside(box.bbox, loop) > 0.5
        }.map(\.index)
    }

    /// A band `[x, y, w, h]` as the loop of its corners.
    static func loop(ofBand band: [Double]) -> [[Double]] {
        guard band.count >= 4 else { return [] }
        let (left, top, right, bottom) = (band[0], band[1], band[0] + band[2], band[1] + band[3])
        return [[left, top], [right, top], [right, bottom], [left, bottom]]
    }

    /// How much of `bbox` is inside `loop`, sampled on a 6×6 grid of cell centres.
    /// ponytail: a sampled share, exact enough for "over half"; an exact clip if a borderline case ever matters.
    static func shareInside(_ bbox: [Double], _ loop: [[Double]]) -> Double {
        guard bbox.count >= 4 else { return 0 }
        let steps = 6
        var hits = 0
        for row in 0..<steps {
            for column in 0..<steps {
                let across = bbox[0] + bbox[2] * (Double(column) + 0.5) / Double(steps)
                let down = bbox[1] + bbox[3] * (Double(row) + 0.5) / Double(steps)
                if contains(loop, across, down) { hits += 1 }
            }
        }
        return Double(hits) / Double(steps * steps)
    }

    /// Even-odd point in polygon.
    static func contains(_ loop: [[Double]], _ across: Double, _ down: Double) -> Bool {
        var inside = false
        var previous = loop[loop.count - 1]
        for point in loop {
            if (point[1] > down) != (previous[1] > down),
               across < (previous[0] - point[0]) * (down - point[1]) / (previous[1] - point[1]) + point[0] {
                inside.toggle()
            }
            previous = point
        }
        return inside
    }

    /// ⌘⇧A: every box whose segment is of a kind the selection holds (`kinds[i]` is box i's segment kind, nil for a
    /// box that is not a segment). Nothing selected selects nothing.
    static func sameKind(as selected: [Int], kinds: [String?]) -> [Int] {
        let wanted = Set(selected.compactMap { kinds.indices.contains($0) ? kinds[$0] : nil })
        guard !wanted.isEmpty else { return [] }
        return kinds.indices.filter { kinds[$0].map(wanted.contains) == true }
    }
}
