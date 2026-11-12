import Foundation

/// The Segments pane's filter (`source.editor.segments-list-has-a-filter-bar`, #6476): a query and facets in, the rows to
/// show out. A row shows when it matches; its ancestors show with it, so a line keeps its region. Pure, one rule for every
/// lens; the bar under the list and its menu only set these values.
struct SegmentsFilter: Equatable {
    enum Reading: String, CaseIterable, Identifiable {
        case has, none, person, machine
        var id: String { rawValue }

        var title: String {
            switch self {
            case .has: "Has a Reading"
            case .none: "No Reading"
            case .person: "A Person's"
            case .machine: "A Machine's"
            }
        }
    }

    /// Matched against the segment's words and its kind, case- and accent-blind.
    var query = ""
    /// Kinds to keep, lowercased; empty keeps every kind.
    var kinds: Set<String> = []
    var reading: Reading?
    var flaggedOnly = false
    var doubtfulOnly = false
    /// Values to keep, own or inherited from a parent segment; empty keeps any.
    var languages: Set<String> = []
    var scripts: Set<String> = []
    var directions: Set<String> = []

    var isActive: Bool { self != SegmentsFilter() }

    /// The trimmed query, nil when there is none.
    private var needle: String? {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// What the filter leaves: the rows that match, and every row to show (those and their ancestors).
    struct Result: Equatable {
        let matched: Set<String>
        let shown: Set<String>
    }

    func apply(to segments: [Segment], flagged: Set<String> = []) -> Result {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let matched = Set(segments.filter { matches($0, in: segments, flagged: flagged.contains($0.id)) }.map(\.id))
        var shown = matched
        for id in matched {
            var cursor = byId[id]?.parentSegmentId
            var hops = 0
            while let parent = cursor, hops < 8, shown.insert(parent).inserted {
                cursor = byId[parent]?.parentSegmentId
                hops += 1
            }
        }
        return Result(matched: matched, shown: shown)
    }

    func matches(_ segment: Segment, in segments: [Segment], flagged: Bool = false) -> Bool {
        if !kinds.isEmpty, !kinds.contains(segment.kind.lowercased()) { return false }
        if flaggedOnly, !flagged { return false }
        let facts = SegmentRowFacts.of(segment, in: segments)
        if doubtfulOnly, !facts.reading.isDoubtful { return false }
        if let reading, !Self.reading(facts.reading, is: reading) { return false }
        if !languages.isEmpty, !languages.contains(facts.language?.value ?? "") { return false }
        if !scripts.isEmpty, !scripts.contains(facts.script?.value ?? "") { return false }
        if !directions.isEmpty, !directions.contains(facts.direction?.value ?? "") { return false }
        guard let needle else { return true }
        let haystack = [segment.text ?? "", segment.kind, segment.kindRaw ?? ""].joined(separator: " ")
        return haystack.range(of: needle, options: [.caseInsensitive, .diacriticInsensitive]) != nil
    }

    private static func reading(_ state: SegmentRowFacts.ReadingState, is wanted: Reading) -> Bool {
        switch (wanted, state) {
        case (.has, .person), (.has, .machine), (.has, .doubtful): true
        case (.none, .none): true
        case (.person, .person): true
        case (.machine, .machine), (.machine, .doubtful): true
        default: false
        }
    }

    /// "12 of 34": how many rows match, of how many the page holds at the levels listed.
    static func countLine(matched: Int, of total: Int) -> String { "\(matched) of \(total)" }
}

extension SegmentRowFacts.ReadingState {
    var isDoubtful: Bool { if case .doubtful = self { true } else { false } }
}
