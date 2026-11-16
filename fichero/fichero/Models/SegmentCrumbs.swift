import Foundation

/// The tail of a pane's path for what is SELECTED on the page (`source.editor.order-list-selection-shows-everywhere`,
/// Step 1.25): "Region 1 › Line 2" for one segment; for several, the path they share and a count, "3 lines". So the
/// head says what the window acts on, in the words the lists use.
enum SegmentCrumbs {
    struct Crumb: Equatable {
        let segmentId: String?
        let title: String
    }

    static func trail(selected ids: [String], in segments: [Segment]) -> [Crumb] {
        guard !ids.isEmpty else { return [] }
        if ids.count == 1 {
            return InspectorPath.to(ids[0], in: segments)?.crumbs.map { step in
                Crumb(segmentId: step.segmentId, title: label(step.segmentId, kind: step.label, in: segments))
            } ?? []
        }
        let shared = InspectorPath.common(ids, in: segments)?.crumbs.map { step in
            Crumb(segmentId: step.segmentId, title: label(step.segmentId, kind: step.label, in: segments))
        } ?? []
        let counts = InspectorPath.kindCounts(ids, in: segments).map { "\($0.count) \($0.kind.lowercased())\($0.count == 1 ? "" : "s")" }
        return shared + [Crumb(segmentId: nil, title: counts.joined(separator: ", "))]
    }

    /// "Line 2": the kind and the segment's place among its parent's children of that kind, as the lists number them.
    private static func label(_ id: String, kind: String, in segments: [Segment]) -> String {
        guard let segment = segments.first(where: { $0.id == id }), segment.cell == nil else { return kind }
        let siblings = segments.filter { $0.parentSegmentId == segment.parentSegmentId && $0.kind == segment.kind }
        guard let place = siblings.firstIndex(where: { $0.id == id }) else { return kind }
        return "\(kind) \(place + 1)"
    }
}
