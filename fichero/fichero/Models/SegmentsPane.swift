import Foundation

/// The Segments pane (`segment-editor.md` "The Segments pane", approved 2026-09-27; #4942): the
/// segments of the page in scope as a list, BESIDE the Preview. Its list, its reorder verbs and its
/// selection are the Order list's own (`ReadingOrderList`, one implementation: Q5's third place);
/// this is what the pane adds -- where it is in the page, and which rows open to their children.
/// Pure: the rules live where a test can reach them.
enum SegmentsPane {
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

    /// A row's words: its kind, then its reading when it has one ("Line · ܐܒܪܗܡ…").
    static func rowLabel(_ segment: Segment?, at index: Int) -> String {
        let kind = segment.map(InspectorPath.name(of:)) ?? "Segment"
        guard let text = segment?.text?.trimmingCharacters(in: .whitespaces), !text.isEmpty else {
            // A cell is named by its place already; a count after it would read as another number.
            return segment?.cell != nil ? kind : "\(kind) \(index + 1)"
        }
        return "\(kind) · \(text)"
    }
}
