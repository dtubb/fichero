import Foundation

/// The selection gestures on the page in Select (`segment-editor.select-marquee-lasso`, `segment-editor.select-shift-toggles`),
/// as pure rules so they are tested as decisions. Points are the page's fractions.
enum SegmentSelectionGestures {
    /// One box on the page: its index in the full list, its `[x, y, w, h]`, its level (`OCRGeometryBox.level`).
    struct Box {
        let index: Int
        let bbox: [Double]
        let level: String
        /// The segment this box draws and the one it sits in (`OCRGeometryBox.segmentId`, `.parentSegmentId`).
        var segmentId: String?
        var parentId: String?

        init(index: Int, bbox: [Double], level: String, segmentId: String? = nil, parentId: String? = nil) {
            self.index = index
            self.bbox = bbox
            self.level = level
            self.segmentId = segmentId
            self.parentId = parentId
        }
    }

    /// The band's hits: the boxes it touches at `level`, plus every region it wholly encloses
    /// (`segment-editor.select-band-encloses-region`). A band inside a region touches only that region's lines.
    static func bandHits(band: [Double], boxes: [Box], level: String?) -> [Int] {
        guard band.count >= 4 else { return [] }
        var hits = touching(band: band, boxes: boxes, level: level)
        for box in boxes where box.level == "region" && box.bbox.count >= 4 && !hits.contains(box.index) {
            if box.bbox[0] >= band[0], box.bbox[1] >= band[1],
               box.bbox[0] + box.bbox[2] <= band[0] + band[2], box.bbox[1] + box.bbox[3] <= band[1] + band[3] {
                hits.append(box.index)
            }
        }
        return hits
    }

    /// `index` with what comes with it: a region brings its lines (by parent segment when the lines carry one, else the
    /// lines whose box lies inside the region's); any other box is alone. The one rule for click, ⇧-click, ⌘-click and band.
    static func group(of index: Int, boxes: [Box]) -> [Int] {
        guard let box = boxes.first(where: { $0.index == index }), box.level == "region" else { return [index] }
        let lines = boxes.filter { line in
            guard line.level == "line" else { return false }
            if let parent = line.parentId, let own = box.segmentId { return parent == own }
            return line.bbox.count >= 4 && box.bbox.count >= 4
                && line.bbox[0] >= box.bbox[0] && line.bbox[1] >= box.bbox[1]
                && line.bbox[0] + line.bbox[2] <= box.bbox[0] + box.bbox[2]
                && line.bbox[1] + line.bbox[3] <= box.bbox[1] + box.bbox[3]
        }.map(\.index)
        return [index] + lines.filter { $0 != index }
    }

    /// `hits` with each region's lines added, order kept, no repeats.
    static func withLines(_ hits: [Int], boxes: [Box]) -> [Int] {
        var out: [Int] = []
        for hit in hits { for member in group(of: hit, boxes: boxes) where !out.contains(member) { out.append(member) } }
        return out
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

    /// The boxes at `level` (nil: any) a rubber band `[x, y, w, h]` touches or encloses: any overlap selects.
    static func touching(band: [Double], boxes: [Box], level: String?) -> [Int] {
        guard band.count >= 4 else { return [] }
        return boxes.filter { box in
            guard level == nil || box.level == level, box.bbox.count >= 4 else { return false }
            return box.bbox[0] <= band[0] + band[2] && band[0] <= box.bbox[0] + box.bbox[2]
                && box.bbox[1] <= band[1] + band[3] && band[1] <= box.bbox[1] + box.bbox[3]
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

    /// The Brush (`segment-editor.select-brush`): the boxes at `level` (nil: any) the painted stroke touches, a stroke
    /// being its points (page fractions) each with the brush's radius, given per axis in page fractions since a screen
    /// circle is an ellipse on a page that is not square.
    static func touched(by stroke: [[Double]], radius: [Double], boxes: [Box], level: String?) -> [Int] {
        guard !stroke.isEmpty, radius.count >= 2, radius[0] > 0, radius[1] > 0 else { return [] }
        return boxes.filter { box in
            guard level == nil || box.level == level, box.bbox.count >= 4 else { return false }
            return stroke.contains { point in
                // The nearest point of the box to the brush's centre, then the distance in brush radii.
                let nearX = min(max(point[0], box.bbox[0]), box.bbox[0] + box.bbox[2])
                let nearY = min(max(point[1], box.bbox[1]), box.bbox[1] + box.bbox[3])
                let across = (point[0] - nearX) / radius[0], down = (point[1] - nearY) / radius[1]
                return across * across + down * down <= 1
            }
        }.map(\.index)
    }

    /// Next Doubtful (`segment-editor.low-confidence-lens`): the doubtful line after `current` in the lens's order, from
    /// the top again after the last; the first when the selection is not one of them; nil when nothing is doubtful.
    static func nextDoubtful(after current: String?, in doubtful: [String]) -> String? {
        guard !doubtful.isEmpty else { return nil }
        guard let current, let index = doubtful.firstIndex(of: current) else { return doubtful[0] }
        return doubtful[(index + 1) % doubtful.count]
    }

    /// ⌘⇧A: every box whose segment is of a kind the selection holds (`kinds[i]` is box i's segment kind, nil for a
    /// box that is not a segment). Nothing selected selects nothing.
    static func sameKind(as selected: [Int], kinds: [String?]) -> [Int] {
        let wanted = Set(selected.compactMap { kinds.indices.contains($0) ? kinds[$0] : nil })
        guard !wanted.isEmpty else { return [] }
        return kinds.indices.filter { kinds[$0].map(wanted.contains) == true }
    }
}
