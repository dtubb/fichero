import Foundation

/// An edited line is read again by itself (`segment-actions.automatic-rerun-after-an-edit`, #6069). The edit runner
/// names the lines a shape edit touched; after a pause with no further edit (never while a drag goes on) they are sent
/// once to `POST /api/recipes/project/reread-edited`. A line a paid cloud model read is never run: it is marked, and the
/// person reads it again with the button.
enum SegmentReread {
    /// The lines a call changed the shape of: a move or resize (`segment.update`), a join (the kept line), a cut (the
    /// lines the stroke was drawn across). Any other call changes no shape.
    static func affectedIds(_ call: SegmentEdit.Call) -> [String] {
        switch call.params {
        case .update(let request): return [request.segmentId]
        case .merge(let request): return [request.keepId]
        // ponytail: every line the stroke was offered to, cut or not; the engine's answer does not name the cut ones.
        case .knife(let request): return request.expectedVersions.keys.sorted()
        default: return []
        }
    }

    /// What the page says under a line whose reading is out of date.
    static let staleWords = "Text may be out of date: Read again"
    static let againTitle = "Read Again"
}
