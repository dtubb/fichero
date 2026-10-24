import Foundation

/// `hand.attribute_many`: these lines' ink is this hand's. `certainty` is optional, 0-1.
struct BulkAttributeHand: Encodable, Equatable {
    let handId: String
    let segmentIds: [String]
    var certainty: Double?

    enum CodingKeys: String, CodingKey { case handId = "hand_id", segmentIds = "segment_ids", certainty }
}

/// `editorial.record_many`: one editorial fact (unclear, lost, ...) on each whole line.
struct BulkRecordEditorial: Encodable, Equatable {
    let segmentIds: [String]
    let kind: String
    var certainty: Double?

    enum CodingKeys: String, CodingKey { case segmentIds = "segment_ids", kind, certainty }
}

/// `rights.set_many`: the same rights record on each line.
struct BulkSetRights: Encodable, Equatable {
    struct Target: Encodable, Equatable {
        let kind = "segment"
        let id: String
    }

    let targets: [Target]
    var holders: [String] = []
    var conditions: String?
    var restricted = false
    var readers: [String] = []
    var modelUse: String?

    enum CodingKeys: String, CodingKey {
        case targets, holders, conditions, restricted, readers, modelUse = "model_use"
    }
}

/// The multi-selection's Hands, Certainty and Rights, each ONE audited action over every selected line
/// (`source.inspector.multi-selection.acts-at-once`, #6082): the engine's `hand.attribute_many`,
/// `editorial.record_many` and `rights.set_many`. Pure: it names the action and builds its params, so the
/// Inspector runs it with `AuditedAction` (one step, one ⌘Z) and a test sees exactly what is sent.
/// Provisional lines (ids that are not stored segments) are never sent: the engine refuses them whole.
enum SegmentBulkEdit {
    typealias AttributeHand = BulkAttributeHand
    typealias RecordEditorial = BulkRecordEditorial
    typealias SetRights = BulkSetRights

    /// The engine's own cap on one request (`max_length=500`): a larger selection is refused up front, in words.
    static let cap = 500

    enum Refusal: Error, Equatable {
        case nothingSelected
        case tooMany(Int)

        var words: String {
            switch self {
            case .nothingSelected: "Select a line first."
            case .tooMany(let count): "\(count) lines is more than one step can take (\(SegmentBulkEdit.cap)); select fewer."
            }
        }
    }

    /// The stored lines of a selection, in the order picked; nil when there is nothing to send or too much.
    static func lines(_ ids: [String]) -> Result<[String], Refusal> {
        let stored = ids.filter { !$0.hasPrefix("legacy:") }
        if stored.isEmpty { return .failure(.nothingSelected) }
        if stored.count > cap { return .failure(.tooMany(stored.count)) }
        return .success(stored)
    }

    static func attributeHand(_ handId: String, to ids: [String], certainty: Double? = nil) -> Result<AttributeHand, Refusal> {
        lines(ids).map { AttributeHand(handId: handId, segmentIds: $0, certainty: certainty) }
    }

    static func record(_ kind: String, on ids: [String], certainty: Double? = nil) -> Result<RecordEditorial, Refusal> {
        lines(ids).map { RecordEditorial(segmentIds: $0, kind: kind, certainty: certainty) }
    }

    static func setRights(on ids: [String], restricted: Bool, readers: [String] = [], modelUse: String? = nil,
                          holders: [String] = [], conditions: String? = nil) -> Result<SetRights, Refusal> {
        lines(ids).map { stored in
            SetRights(targets: stored.map { .init(id: $0) }, holders: holders, conditions: conditions,
                      restricted: restricted, readers: readers, modelUse: modelUse)
        }
    }

    /// A step's name in words, counted (`undo.naming.counts`).
    static func stepName(_ verb: String, count: Int) -> String {
        UndoableChange.named(verb, count: count, one: "Line", many: "Lines")
    }
}
