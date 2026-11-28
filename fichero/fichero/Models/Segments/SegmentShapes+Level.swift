import Foundation

/// What the polygon and rectangle tools make (#7083): a region, a line or a word, by the person's choice or, until they
/// choose, by the selection. A baseline is always a line.
extension SegmentShapes {
    enum DrawnLevel: String, CaseIterable, Identifiable {
        case region, line, word
        var id: String { rawValue }
        var title: String { rawValue.capitalized }
        /// The kind of segment that holds one of this level; nil for a region, which sits at page level.
        var parentKind: String? {
            switch self {
            case .region: nil
            case .line: "region"
            case .word: "line"
            }
        }
    }

    /// The level to draw: the chosen one, else one level below a single selected region or line, else a region.
    static func level(chosen: DrawnLevel?, selected: [Segment]) -> DrawnLevel {
        if let chosen { return chosen }
        return addLevel(for: selected) ?? .region
    }

    /// What Add Line (on one region) or Add Word (on one line) draws; nil for any other selection.
    static func addLevel(for selected: [Segment]) -> DrawnLevel? {
        guard selected.count == 1, let only = selected.first else { return nil }
        switch only.kind.lowercased() {
        case "region": return .line
        case "line": return .word
        default: return nil
        }
    }

    /// The segment a drawn shape of `level` goes into: the region (for a line) or the line (for a word) holding most of it.
    static func containingParent(for points: [[Double]], level: DrawnLevel, among segments: [Segment]) -> Segment? {
        guard let kind = level.parentKind else { return nil }
        return containingRegion(for: points, among: segments, kind: kind)
    }

    /// Said when a line is drawn where no region holds it.
    static let noRegionNotice = "This line is in no region"

    /// The kind Change Kind turns a segment into: a region becomes a line and a line a region; nil for any other.
    static func changedKind(of segment: Segment) -> String? {
        switch segment.kind.lowercased() {
        case "region": "line"
        case "line": "region"
        default: nil
        }
    }

    /// Whether Change Kind is offered: something is selected and every selected segment is a region or a line.
    static func offersChangeKind(_ selected: [Segment]) -> Bool {
        !selected.isEmpty && selected.allSatisfy { changedKind(of: $0) != nil }
    }
}
