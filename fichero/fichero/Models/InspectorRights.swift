import Foundation

/// The Inspector's Rights section (`build-notes-inspector.md` 5.8; `source.rights.record`,
/// `tighten-only`, `who-acts`): what applies HERE, worked out by the engine from the library down
/// (`GET /api/rights/effective`), said in words, with the records that added up to it. Records only
/// tighten, so the effect is never looser than any record above. Pure: the words live where a test
/// can reach them.
enum InspectorRights {
    struct Record: Equatable, Identifiable {
        let id: String
        let targetKind: String
        let targetId: String
        var holders: [String] = []
        var conditions: String?
        var labels: [String] = []
        var restricted = false
        var readers: [String] = []
        var modelUse: String?
        var createdBy: String?
    }

    struct Answer: Equatable {
        var restricted = false
        /// Nil when unrestricted: the library's permissions alone decide.
        var readers: [String]?
        var modelUse: String?
        var labels: [String] = []
        /// The live records that contributed, library first.
        var records: [Record] = []
    }

    struct Line: Equatable, Identifiable {
        let title: String
        let value: String
        var id: String { title }
    }

    struct Row: Equatable, Identifiable {
        let recordId: String
        /// "On the library", "On this page", "On this segment".
        let place: String
        /// "local models only · agreement 2026-07 · by owner".
        let detail: String
        var id: String { recordId }
    }

    /// The effect in words: who may see it, where it may be sent, and its labels.
    static func effect(_ answer: Answer) -> [Line] {
        var lines = [
            Line(title: "Who may see it", value: answer.restricted
                 ? "Only " + ((answer.readers ?? []).isEmpty ? "nobody named" : (answer.readers ?? []).joined(separator: ", "))
                 : "Everyone the library's permissions allow"),
            Line(title: "Models", value: modelUseWords(answer.modelUse))
        ]
        if !answer.labels.isEmpty { lines.append(Line(title: "Labels", value: answer.labels.joined(separator: ", "))) }
        return lines
    }

    static func modelUseWords(_ modelUse: String?) -> String {
        switch modelUse {
        case "none": "May not be sent to any model"
        case "local": "Local models only"
        case "cloud": "Local or cloud models"
        case nil: "No rule here; the library's AI settings decide"
        case let other?: other
        }
    }

    /// Each contributing record: where it sits relative to what is inspected, and what it says.
    static func rows(_ records: [Record], targetKind: String, targetId: String, pageId: String) -> [Row] {
        records.map { record in
            var parts: [String] = []
            if record.restricted {
                parts.append("restricted to " + (record.readers.isEmpty ? "nobody named" : record.readers.joined(separator: ", ")))
            }
            if let use = record.modelUse { parts.append(modelUseWords(use).lowercased()) }
            if !record.labels.isEmpty { parts.append("labels: " + record.labels.joined(separator: ", ")) }
            if !record.holders.isEmpty { parts.append("held by " + record.holders.joined(separator: ", ")) }
            if let conditions = record.conditions { parts.append(conditions) }
            if let author = record.createdBy { parts.append("by \(author)") }
            return Row(recordId: record.id, place: place(of: record, targetKind: targetKind, targetId: targetId, pageId: pageId),
                       detail: parts.joined(separator: " · "))
        }
    }

    static func place(of record: Record, targetKind: String, targetId: String, pageId: String) -> String {
        switch record.targetKind {
        case "library": "On the library"
        case "document" where record.targetId == pageId: "On this page"
        case "document": "On a folder above"
        case "segment" where record.targetKind == targetKind && record.targetId == targetId: "On this segment"
        default: "On an enclosing segment"
        }
    }

    /// The Set menu's model rules, strictest first.
    static let modelUses: [(value: String, title: String)] = [
        ("none", "No Models"), ("local", "Local Models Only"), ("cloud", "Local or Cloud Models")
    ]
}

/// `rights.set`: one new record on a target. Only the facts being set are sent.
struct RightsSetRequest: Encodable, Equatable {
    let targetKind: String
    let targetId: String
    var labels: [String]?
    var modelUse: String?

    enum CodingKeys: String, CodingKey {
        case targetKind = "target_kind", targetId = "target_id", labels, modelUse = "model_use"
    }

    func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(targetKind, forKey: .targetKind)
        try container.encode(targetId, forKey: .targetId)
        try container.encodeIfPresent(labels, forKey: .labels)
        try container.encodeIfPresent(modelUse, forKey: .modelUse)
    }
}

/// `rights.withdraw`: withdraw one record (kept, never deleted; ⌘Z restores it).
struct RightsRecordIdRequest: Encodable, Equatable {
    let recordId: String

    enum CodingKeys: String, CodingKey { case recordId = "record_id" }
}
