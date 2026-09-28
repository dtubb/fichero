import Foundation

/// A GATHERED set in the Segments pane (`source.segments-pane.gathers`, #4942): segments that are not
/// one page's -- everything in one hand, every instance of one sign -- asked for from the Inspector
/// ("Everything in This Hand", "Every Instance") and shown in the pane. Only what the caller may read
/// is listed; what the engine leaves out is counted and SAID (#5180), never silently missing.
enum SegmentsGather: Equatable {
    case hand(id: String, label: String)
    case sign(id: String, name: String)

    var title: String {
        switch self {
        case .hand(_, let label): "Everything in \(label)"
        case .sign(_, let name): "Every instance of \(name)"
        }
    }
}

/// The rows of a gathered set. Pure: the words live where a test can reach them.
enum SegmentsGathered {
    struct Row: Equatable, Identifiable {
        let id: String
        let segmentId: String?
        /// The page the row opens in the Preview; nil when the segment could not be read.
        let documentId: String?
        let title: String
        let detail: String
    }

    struct Answer: Equatable {
        var rows: [Row] = []
        /// How many the engine left out because this reader may not read their pages.
        var withheld = 0
    }

    /// One use of a sign: a reading that has it, on a page.
    struct SignUse: Equatable {
        let representationId: String
        let segmentId: String?
        let documentId: String
        let count: Int
    }

    /// Everything attributed to one hand, each row the segment's words and the judgement's.
    static func handRows(_ attributions: [InspectorHands.Attribution], segments: [String: Segment]) -> [Row] {
        attributions.enumerated().map { index, attribution in
            let segment = attribution.segmentId.flatMap { segments[$0] }
            var parts: [String] = []
            if let file = attribution.fromFile {
                parts.append(file.hasPrefix("file: ") ? "from the file \(file.dropFirst("file: ".count))" : file)
            } else if let judge = attribution.judgedBy {
                parts.append("judged by \(judge)")
            }
            if let certainty = attribution.certainty { parts.append("sure \(Int((certainty * 100).rounded()))%") }
            if segment == nil { parts.append("its segment could not be read") }
            return Row(
                id: attribution.id, segmentId: attribution.segmentId, documentId: segment?.documentId,
                title: SegmentsPane.rowLabel(segment, at: index), detail: parts.joined(separator: " · ")
            )
        }
    }

    /// Every use of one sign, each row the segment's words and how often the sign occurs in it.
    static func signRows(_ uses: [SignUse], segments: [String: Segment]) -> [Row] {
        uses.enumerated().map { index, use in
            let segment = use.segmentId.flatMap { segments[$0] }
            return Row(
                id: use.representationId, segmentId: use.segmentId, documentId: use.documentId,
                title: SegmentsPane.rowLabel(segment, at: index),
                detail: use.count == 1 ? "once" : "\(use.count) times"
            )
        }
    }

    /// "3 more on pages you may not read" -- or nothing when none were left out.
    static func withheldNote(_ withheld: Int) -> String? {
        switch withheld {
        case ..<1: nil
        case 1: "1 more on a page you may not read"
        default: "\(withheld) more on pages you may not read"
        }
    }
}
