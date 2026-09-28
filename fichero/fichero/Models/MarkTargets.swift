import Foundation

/// What a mark made on the SELECTION is attached to (Q6, ruled 2026-09-27: a mark applies to the
/// selection, or attaches to whatever it is drawn over; `build-notes-marks-pdfkit.md`). The mark still
/// carries the strip it is drawn at; `targets` says which segments it is ABOUT, so it follows them
/// rather than a rectangle that may since have moved.
enum MarkTargets {
    /// The Source view's selection on one page as (segment id, box), in the order picked, through the
    /// one resolution the Inspector uses (`InspectorPath.selectedSegmentIds`).
    @MainActor
    static func selectedSegments(
        selection: RegionSelection, documentId: String, store: SegmentStore
    ) -> [(id: String, rect: [Double])] {
        let ids = InspectorPath.selectedSegmentIds(selection: selection, documentId: documentId, store: store)
        let rects = Dictionary(
            store.segments(documentId: documentId).compactMap { seg in seg.anchor.rect.map { (seg.id, $0) } },
            uniquingKeysWith: { first, _ in first }
        )
        return ids.compactMap { id in rects[id].map { (id: id, rect: $0) } }
    }

    /// The selected segments one strip covers -- a highlight over a selection is one strip per line,
    /// and each strip is attached to the segments it is drawn OVER, not to the whole selection.
    ///
    /// "Over" is at least half of one of the two boxes, by area: real line boxes overlap their
    /// neighbours (on the imported Syriac page, line 1's box reaches 5% into line 2's), so a strip on
    /// line 1 merely touching line 2 must not attach to it.
    static func segmentIds(in strip: [Double], selected: [(id: String, rect: [Double])]) -> [String] {
        guard strip.count == 4 else { return [] }
        return selected.filter { segment in
            let rect = segment.rect
            guard rect.count == 4 else { return false }
            let width = min(rect[0] + rect[2], strip[0] + strip[2]) - max(rect[0], strip[0])
            let height = min(rect[1] + rect[3], strip[1] + strip[3]) - max(rect[1], strip[1])
            guard width > 0, height > 0 else { return false }
            let smaller = min(rect[2] * rect[3], strip[2] * strip[3])
            return smaller > 0 && width * height >= 0.5 * smaller
        }.map(\.id)
    }
}
