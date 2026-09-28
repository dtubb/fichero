import FicheroAPIClient
import Foundation

/// A GATHERED set in the Segments pane (`source.segments-pane.gathers`, #4942): segments that are not
/// one page's -- everything in one hand, every instance of one sign -- asked for from the Inspector
/// ("Everything in This Hand", "Every Instance") and shown in the pane. Only what the caller may read
/// is listed; what the engine leaves out is counted and SAID (#5180), never silently missing.
enum SegmentsGather: Equatable {
    case hand(id: String, label: String)
    case sign(id: String, name: String)
    /// A page's proposed matches, to accept or reject (#5165, `source.segment.match-record`).
    case matches(documentId: String)

    var title: String {
        switch self {
        case .hand(_, let label): "Everything in \(label)"
        case .sign(_, let name): "Every instance of \(name)"
        case .matches: "Proposed matches"
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
        /// A proposed match's id: the row offers Accept and Reject (#5165).
        var matchId: String?
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

    /// One proposed match: "this newer segment is that older one" (`SegmentMatch`).
    struct Match: Equatable {
        let id: String
        let fromSegmentId: String
        let toSegmentId: String
        let proposedBy: String?
        let certainty: Double?
        let note: String?
    }

    /// A page's proposed matches, each row the newer segment, saying what it was matched to, who
    /// proposed it and how sure; the row opens the newer segment.
    static func matchRows(_ matches: [Match], documentId: String, segments: [String: Segment]) -> [Row] {
        matches.enumerated().map { index, match in
            var parts = ["was " + SegmentsPane.rowLabel(segments[match.fromSegmentId], at: index)]
            if let proposedBy = match.proposedBy { parts.append("proposed by \(proposedBy)") }
            if let certainty = match.certainty { parts.append("sure \(Int((certainty * 100).rounded()))%") }
            if let note = match.note { parts.append(note) }
            return Row(
                id: match.id, segmentId: match.toSegmentId, documentId: documentId,
                title: SegmentsPane.rowLabel(segments[match.toSegmentId], at: index),
                detail: parts.joined(separator: " · "), matchId: match.id
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

/// `segment.match_accept` / `segment.match_reject`: one match, by id.
struct SegmentMatchIdRequest: Encodable, Equatable {
    let matchId: String

    enum CodingKeys: String, CodingKey { case matchId = "match_id" }
}

extension SegmentService {
    /// A page's matches still to review (`GET /api/segments/document/{id}/matches?state=proposed`).
    func proposedMatches(documentId: String) async throws -> [SegmentsGathered.Match] {
        let response = try await client.api.listDocumentMatchesApiSegmentsDocumentDocIdMatchesGet(
            path: .init(docId: documentId), query: .init(state: "proposed")
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map {
                SegmentsGathered.Match(
                    id: $0.id ?? "", fromSegmentId: $0.fromSegmentId, toSegmentId: $0.toSegmentId,
                    proposedBy: $0.proposedBy, certainty: $0.certainty, note: $0.note
                )
            }
        case .unprocessableContent:
            return []
        case .undocumented(let statusCode, _):
            throw SegmentServiceError.unexpectedResponse(statusCode)
        }
    }
}
