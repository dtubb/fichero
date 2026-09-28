import Foundation

/// The Segments pane (`segment-editor.md` "The Segments pane", approved 2026-09-27; #4942): the
/// segments of the page in scope as a list, BESIDE the Preview. Its list, its reorder verbs and its
/// selection are the Order list's own (`ReadingOrderList`, one implementation: Q5's third place);
/// this is what the pane adds -- where it is in the page, and which rows open to their children.
/// Pure: the rules live where a test can reach them.
enum SegmentsPane {
    /// What the list half of the pane shows. Never an indefinite spinner: loading only while the order
    /// store is being made from a service that is THERE; a window whose environment lacks the service
    /// says so (2026-09-28: the main window's tree lacked ReadingOrderService and the pane spun forever).
    enum ListState: Equatable { case noPage, loading, list, unavailable }

    static func listState(hasDocument: Bool, hasOrders: Bool, hasOrderService: Bool) -> ListState {
        guard hasDocument else { return .noPage }
        if hasOrders { return .list }
        return hasOrderService ? .loading : .unavailable
    }

    /// How the pane shows its segments: a list, or a strip or a grid of their pictures
    /// (`source.segments-pane.views`).
    enum Lens: String, CaseIterable, Identifiable, Hashable {
        case list, strip, grid
        var id: String { rawValue }

        var title: String {
            switch self {
            case .list: "List"
            case .strip: "Strip"
            case .grid: "Grid"
            }
        }

        var icon: String {
            switch self {
            case .list: "list.bullet"
            case .strip: "rectangle.split.3x1"
            case .grid: "square.grid.2x2"
            }
        }
    }

    /// One step of the path from the page down to the level shown.
    struct Step: Equatable, Identifiable {
        /// Nil for the page itself.
        let segmentId: String?
        let title: String
        var id: String { segmentId ?? "page" }
    }

    /// Whether a row can be opened: the segment has children on this page.
    /// One level of a page with no named order, as the page holds it (#5204): the children of `parentId`,
    /// or with nil the segments whose parent is not on the page, in the order the engine serves them
    /// (a box's own index, else creation) -- the file's order, never re-sorted here.
    static func asWritten(_ segments: [Segment], under parentId: String?) -> [String] {
        let onPage = Set(segments.map(\.id))
        return segments.filter { segment in
            guard let parentId else { return segment.parentSegmentId.map { !onPage.contains($0) } ?? true }
            return segment.parentSegmentId == parentId
        }.map(\.id)
    }

    /// The order's level when it has one, else the level as written: the strip and grid show what the list does.
    static func shownOrAsWritten(_ shown: [String]?, _ segments: [Segment], under parentId: String?) -> [String] {
        if let shown, !shown.isEmpty { return shown }
        return asWritten(segments, under: parentId)
    }

    static func hasChildren(_ segmentId: String, in segments: [Segment]) -> Bool {
        segments.contains { $0.parentSegmentId == segmentId }
    }

    /// The path to the level shown: the page, then each segment down to `parentId`, named by kind
    /// ("Region", "Line") as the Inspector's path head names them.
    static func path(pageTitle: String, to parentId: String?, in segments: [Segment]) -> [Step] {
        var steps = [Step(segmentId: nil, title: pageTitle)]
        if let parentId, let path = InspectorPath.to(parentId, in: segments) {
            steps += path.crumbs.map { Step(segmentId: $0.segmentId, title: $0.label) }
        }
        return steps
    }

    /// The kinds that carry a reading of their own. A region or a table does not (its words are its
    /// lines'), so it is never marked "No reading".
    static let readingKinds: Set<String> = ["line", "word", "character", "glyph"]

    /// A segment left WITHOUT a reading (`source.textedit.deleting-words-keeps-ink`): one of the reading
    /// kinds with no counting transcription at all -- a line drawn by its baseline, a word a segmenter
    /// found. Shown as such, never hidden. An EMPTIED line is not this: it has a reading, an empty one.
    static func lacksReading(_ segment: Segment) -> Bool {
        segment.text == nil && readingKinds.contains(segment.kind.lowercased())
    }

    /// A row's words: its kind, then its reading when it has one ("Line · ܐܒܪܗܡ…").
    static func rowLabel(_ segment: Segment?, at index: Int) -> String {
        let kind = segment.map(InspectorPath.name(of:)) ?? "Segment"
        guard let text = segment?.text?.trimmingCharacters(in: .whitespaces), !text.isEmpty else {
            // A cell is named by its place already; a count after it would read as another number.
            let named = segment?.cell != nil ? kind : "\(kind) \(index + 1)"
            return segment.map(lacksReading) == true ? named + " · No reading" : named
        }
        return "\(kind) · \(text)"
    }
}

/// `segment.convert_and_edit` with no edit: the page's boxes become segments and its `as-written` order is
/// made from their order, one action with ⌘Z. What "Create Named Order" sends when the page has no order to
/// copy (#5204).
struct ConvertPageRequest: Encodable, Equatable {
    let documentId: String

    enum CodingKeys: String, CodingKey { case documentId = "document_id" }
}
