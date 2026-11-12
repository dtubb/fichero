import Foundation

/// Tab and Shift-Tab in the nested Order list (#6476, `source.editor.order-list-indents-with-tab`), as an outliner does
/// it: Tab puts the selected rows into the row just above the first of them at its own level, when that row can hold
/// them (a line into the region above it); Shift-Tab takes them out of their parent, into the parent's own parent.
extension OrderDrop {
    /// Where Shift-Tab puts rows: into `parent` (nil, the page's top level).
    struct Outdent: Equatable {
        let parent: String?
    }

    /// The selected ids in the order the outline shows them.
    static func inOutlineOrder(_ ids: Set<String>, outline: [SegmentsPane.OutlineRow]) -> [String] {
        flatten(outline).filter { ids.contains($0) }
    }

    /// Tab: the row the selection goes into; nil when the row above at the same level cannot hold it (or there is none).
    static func indentTarget(_ ids: [String], outline: [SegmentsPane.OutlineRow], in segments: [Segment]) -> String? {
        guard let first = ids.first, let siblings = siblings(of: first, in: outline),
              let place = siblings.firstIndex(where: { $0.segmentId == first }), place > 0 else { return nil }
        let above = siblings[place - 1].segmentId
        guard !ids.contains(above), let holder = segments.first(where: { $0.id == above }),
              accepted(ids, into: holder, in: segments).count == ids.count else { return nil }
        return above
    }

    /// Shift-Tab: where the selection comes out to; nil when it is at the top already or its rows sit under different
    /// parents.
    static func outdentTarget(_ ids: [String], in segments: [Segment]) -> Outdent? {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let parents = Set(ids.map { byId[$0]?.parentSegmentId })
        guard parents.count == 1, let parentId = parents.first ?? nil, let parent = byId[parentId] else { return nil }
        return Outdent(parent: parent.parentSegmentId)
    }

    private static func flatten(_ rows: [SegmentsPane.OutlineRow]) -> [String] {
        rows.flatMap { [$0.segmentId] + flatten($0.children) }
    }

    /// The rows at the same level as `id`, in order.
    private static func siblings(of id: String, in rows: [SegmentsPane.OutlineRow]) -> [SegmentsPane.OutlineRow]? {
        if rows.contains(where: { $0.segmentId == id }) { return rows }
        for row in rows {
            if let found = siblings(of: id, in: row.children) { return found }
        }
        return nil
    }
}
