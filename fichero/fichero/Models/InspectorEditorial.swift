import Foundation

/// The Inspector's Certainty and Damage section (`build-notes-inspector.md` 5.5;
/// `source.sure.editorial-facts`, `source.sure.brackets-are-drawn`): what the editor knows about the
/// state of this text -- unclear, lost, restored, supplied, superfluous, deleted, added -- each a FACT
/// with where it lies, how much, why, who said so and how sure. The text as the editor prints it
/// (Leiden: under-dots, brackets) is DRAWN by the engine from these facts; it is never typed into the
/// reading. Pure: the words live where a test can reach them.
enum InspectorEditorial {
    struct Fact: Equatable, Identifiable {
        let id: String
        let kind: String
        var charStart: Int?
        var charEnd: Int?
        var extent: String?
        var extentQuantity: Double?
        var extentUnit: String?
        var reason: String?
        var place: String?
        /// The scholar's certainty in this judgement, 0-1 -- never a machine's confidence.
        var certainty: Double?
        var createdBy: String?
        /// "file: <name>" when an imported file said so.
        var source: String?
    }

    /// What `GET /api/editorial/segment/{id}` answers: the live facts, and the counting reading with
    /// them drawn in (nil when no reading counts).
    struct Answer: Equatable {
        let facts: [Fact]
        let drawn: String?
    }

    struct Row: Equatable, Identifiable {
        let factId: String
        /// "Unclear", "Lost", "Added by the scribe".
        let title: String
        /// "letters 1–3 · faded · by owner · sure 80%".
        let detail: String
        var id: String { factId }
    }

    /// The verbs on the inspected segment: each marks its WHOLE counting reading. A stretch within a
    /// line is marked where the text is selected, not here (the Inspector types no text).
    enum Mark: String, CaseIterable, Identifiable {
        case unclear, restored, supplied, superfluous, deleted, added
        var id: String { rawValue }

        var title: String {
            switch self {
            case .unclear: "Unclear"
            case .restored: "Restored by the Editor"
            case .supplied: "Supplied (Left Out by the Scribe)"
            case .superfluous: "Superfluous"
            case .deleted: "Deleted by the Scribe"
            case .added: "Added Above the Line"
            }
        }
    }

    static func title(ofKind kind: String) -> String {
        switch kind {
        case "unclear": "Unclear"
        case "lost": "Lost"
        case "restored": "Restored by the editor"
        case "supplied": "Supplied (left out by the scribe)"
        case "superfluous": "Superfluous"
        case "deleted": "Deleted by the scribe"
        case "added": "Added by the scribe"
        default: kind.capitalized
        }
    }

    static func rows(_ facts: [Fact]) -> [Row] {
        facts.map { fact in
            var parts = [whereIt(fact)]
            if let quantity = fact.extentQuantity {
                let count = quantity.rounded() == quantity ? String(Int(quantity)) : String(quantity)
                let unit = fact.extentUnit ?? "character"
                parts.append("\(count) \(quantity == 1 ? unit : unit + "s")")
            } else if let extent = fact.extent {
                parts.append(extent)
            }
            if let place = fact.place { parts.append(placeName(place)) }
            if let reason = fact.reason { parts.append(reason) }
            if let file = fact.source {
                parts.append(file.hasPrefix("file: ") ? "from the file \(file.dropFirst("file: ".count))" : file)
            } else if let author = fact.createdBy {
                parts.append("by \(author)")
            }
            if let certainty = fact.certainty { parts.append("sure \(Int((certainty * 100).rounded()))%") }
            return Row(factId: fact.id, title: title(ofKind: fact.kind), detail: parts.joined(separator: " · "))
        }
    }

    /// Where in the text, counted from 1 as people count letters.
    static func whereIt(_ fact: Fact) -> String {
        switch (fact.charStart, fact.charEnd) {
        case let (start?, end?) where end - start == 1: "letter \(start + 1)"
        case let (start?, end?): "letters \(start + 1)–\(end)"
        case (0?, nil): "at the start"
        case let (start?, nil): "after letter \(start)"
        default: "the whole segment"
        }
    }

    static func placeName(_ place: String) -> String {
        switch place {
        case "above": "above the line"
        case "below": "below the line"
        case "margin": "in the margin"
        default: place
        }
    }

    /// `editorial.record` for a Mark over the whole counting reading: its span in CODE POINTS, what the
    /// engine's strings count. Nil when no reading counts -- there is no text to mark.
    static func record(_ mark: Mark, segmentId: String, reading: InspectorText.Reading?) -> EditorialRecordRequest? {
        guard let reading, !reading.content.isEmpty else { return nil }
        return EditorialRecordRequest(
            segmentId: segmentId, kind: mark.rawValue, representationId: reading.id,
            charStart: 0, charEnd: reading.content.unicodeScalars.count, place: mark == .added ? "above" : nil
        )
    }
}

/// `editorial.record`: one fact about a stretch of one segment's reading.
struct EditorialRecordRequest: Encodable, Equatable {
    let segmentId: String
    let kind: String
    let representationId: String
    let charStart: Int
    let charEnd: Int
    let place: String?

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", kind, representationId = "representation_id"
        case charStart = "char_start", charEnd = "char_end", place
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(segmentId, forKey: .segmentId)
        try container.encode(kind, forKey: .kind)
        try container.encode(representationId, forKey: .representationId)
        try container.encode(charStart, forKey: .charStart)
        try container.encode(charEnd, forKey: .charEnd)
        try container.encodeIfPresent(place, forKey: .place)
    }
}

/// `editorial.withdraw`: withdraw one fact (kept, never deleted).
struct EditorialFactRequest: Encodable, Equatable {
    let factId: String

    enum CodingKeys: String, CodingKey { case factId = "fact_id" }
}
