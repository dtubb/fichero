import Foundation

/// Where a dragged row may land in the nested Order list (`source.editor.order-list-drag-reorders-and-reparents`,
/// Step 1.25): into a segment exactly one level coarser (a line into a region, a word into a line), never into itself
/// or something it holds. One rule for the Order list and the Reader's rows.
/// The engine (`segment.reparent`) checks pass, document, liveness and cycles but NOT the parent's level, so the app checks that.
enum OrderDrop {
    /// The dragged ids that may be dropped INTO `parent`, in the order given; empty when the drop shows no target.
    static func accepted(_ draggedIds: [String], into parent: Segment, in segments: [Segment]) -> [String] {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let parentLevel = SegmentHierarchy.Level(kind: parent.kind)
        return draggedIds.filter { id in
            guard let dragged = byId[id], id != parent.id else { return false }
            guard SegmentHierarchy.Level(kind: dragged.kind).rawValue == parentLevel.rawValue + 1 else { return false }
            return !holds(id, parentId: parent.id, byId: byId)
        }
    }

    /// Whether `ancestorId` is `parentId` or sits above it (dropping a segment into what it holds).
    private static func holds(_ ancestorId: String, parentId: String, byId: [String: Segment]) -> Bool {
        var cursor: String? = parentId
        var hops = 0
        while let current = cursor, hops < 16 {
            if current == ancestorId { return true }
            cursor = byId[current]?.parentSegmentId
            hops += 1
        }
        return false
    }
}
