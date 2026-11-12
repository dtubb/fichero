import Foundation

/// What a Segments row can say about its segment beyond its words (`source.editor.segment-row-shows-its-facts-as-icons`,
/// first slice, #6482): its count, its direction, language and script (own or inherited from a parent segment), and the
/// state of its reading. Computed from the page's segments the store already holds, no call; one model for every lens.
struct SegmentRowFacts: Equatable {
    /// A region counts its lines, a line its words, a word its characters.
    enum Count: Equatable {
        case lines(Int), words(Int), characters(Int)

        var short: String {
            switch self {
            case .lines(let n): "\(n) ln"
            case .words(let n): "\(n) w"
            case .characters(let n): "\(n) ch"
            }
        }

        var words: String {
            switch self {
            case .lines(let n): n == 1 ? "1 line" : "\(n) lines"
            case .words(let n): n == 1 ? "1 word" : "\(n) words"
            case .characters(let n): n == 1 ? "1 character" : "\(n) characters"
            }
        }
    }

    /// A value stated on the segment itself, or on the nearest parent segment that states one.
    struct Stated: Equatable {
        let value: String
        /// The parent segment it came from; nil when the segment states it itself.
        let fromSegmentId: String?
        var inherited: Bool { fromSegmentId != nil }
    }

    enum ReadingState: Equatable {
        /// A kind that is read (a line, a word) with no reading yet.
        case none
        /// A person made or corrected it.
        case person
        /// A machine's, below the confidence floor: the confidence, 0 to 1.
        case doubtful(Double)
        /// A machine's, at or above the floor, or with no confidence given.
        case machine
        /// A kind that holds readings in its children (a region) or none at all.
        case notRead
    }

    let count: Count?
    let direction: Stated?
    let language: Stated?
    let script: Stated?
    let reading: ReadingState

    /// A machine's reading below this is shown as doubtful.
    static let confidenceFloor = 0.8

    static func of(_ segment: Segment, in segments: [Segment], confidenceFloor: Double = confidenceFloor) -> SegmentRowFacts {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let children = segments.filter { $0.parentSegmentId == segment.id }
        return SegmentRowFacts(
            count: count(segment, children: children),
            direction: stated(segment, byId: byId, \.direction),
            language: stated(segment, byId: byId, \.language),
            script: stated(segment, byId: byId, \.script),
            reading: reading(segment, floor: confidenceFloor)
        )
    }

    private static func count(_ segment: Segment, children: [Segment]) -> Count? {
        let text = segment.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        switch segment.kind.lowercased() {
        case "region", "block", "column", "table":
            let lines = children.filter { $0.kind.lowercased() == "line" }.count
            return lines > 0 ? .lines(lines) : nil
        case "line":
            let words = text.split(whereSeparator: \.isWhitespace).count
            if words > 0 { return .words(words) }
            let wordChildren = children.filter { $0.kind.lowercased() == "word" }.count
            return wordChildren > 0 ? .words(wordChildren) : nil
        case "word":
            return text.isEmpty ? nil : .characters(text.filter { !$0.isWhitespace }.count)
        default:
            return nil
        }
    }

    /// The segment's own value, else the nearest parent segment's (a word takes its line's, a line its region's).
    /// The page, document and project rungs are the engine's (`source.lang.cascade`); this walks the segments only.
    private static func stated(_ segment: Segment, byId: [String: Segment], _ value: KeyPath<Segment, String?>) -> Stated? {
        if let own = segment[keyPath: value], !own.isEmpty { return Stated(value: own, fromSegmentId: nil) }
        var cursor = segment.parentSegmentId
        var hops = 0
        while let parentId = cursor, let parent = byId[parentId], hops < 8 {
            if let found = parent[keyPath: value], !found.isEmpty { return Stated(value: found, fromSegmentId: parent.id) }
            cursor = parent.parentSegmentId
            hops += 1
        }
        return nil
    }

    private static func reading(_ segment: Segment, floor: Double) -> ReadingState {
        guard SegmentsPane.readingKinds.contains(segment.kind.lowercased()) else { return .notRead }
        guard let text = segment.text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return .none }
        if segment.isHandCurated { return .person }
        if let confidence = segment.confidence, confidence < floor { return .doubtful(confidence) }
        return .machine
    }
}
