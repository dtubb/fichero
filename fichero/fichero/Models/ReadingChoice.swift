import Foundation

/// "Make This Count": a person chooses which reading of a segment counts for its kind (#5153;
/// `source.reading.chosen-is-worked-out`). Two people's readings of one line are equal until one is
/// chosen (`source.reading.equal-alternatives`), so this is the verb that settles it -- through the
/// audited `reading.choose`, undoable with ⌘Z. It types nothing (the Inspector never does, ruled).
enum ReadingChoice {
    typealias Params = ReadingChooseParams

    /// The call, or nil when the reading already counts -- choosing it again would write an audited
    /// action that changed nothing.
    static func choose(_ reading: InspectorText.Reading, of segmentId: String, in text: InspectorText) -> Params? {
        guard !text.counts(reading) else { return nil }
        return Params(segmentId: segmentId, kind: reading.kind, representationId: reading.id)
    }

    /// Send it, register ⌘Z by its own audit id, and call `afterChange` (re-read the readings) after
    /// the choice and after each undo / redo. Answers the audit id.
    @MainActor
    @discardableResult
    static func run(
        _ params: Params, actionsService: ActionsService, steps: WindowSteps?,
        afterChange: @escaping @MainActor () async -> Void
    ) async throws -> String {
        let result = try await AuditedAction.run(
            "reading.choose", params: params, actionName: "Choose Reading", actionsService: actionsService,
            steps: steps, afterChange: afterChange
        )
        return result.auditId
    }
}

/// `reading.choose`'s params (top level: SwiftLint's nesting rule counts CodingKeys).
struct ReadingChooseParams: Encodable, Equatable {
    let segmentId: String
    let kind: String
    let representationId: String

    enum CodingKeys: String, CodingKey {
        case segmentId = "segment_id", kind, representationId = "representation_id"
    }
}
