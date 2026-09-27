import FicheroAPIClient
import Foundation

/// What a claim editor sends when it saves: ONE definition for `EditClaimSheet` and
/// `InlineClaimEditor` (#4833), so their trimming and "send only what changed" rules cannot
/// drift apart, and so the payload is a value a test can read instead of source to scan.
struct ClaimPatchFields: Equatable {
    var text: String?
    var subjectCanonical: String?
    var subjectEntityId: String?
    var predicateVerb: String?
    var objectPhrase: String?
    var sourcePageLabel: String?
    var claimType: Components.Schemas.ClaimType?
    var epistemicStatus: Components.Schemas.EpistemicStatus?
    var timeStart: String?
    var timeEnd: String?
    var timePrecision: String?

    static func trimmedOrNil(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// The full-sheet editor: free text plus a typed subject NAME.
    static func sheet(_ draft: ClaimDraft) -> ClaimPatchFields {
        ClaimPatchFields(
            text: draft.text.trimmingCharacters(in: .whitespacesAndNewlines),
            subjectCanonical: trimmedOrNil(draft.subject),
            predicateVerb: trimmedOrNil(draft.predicate),
            objectPhrase: trimmedOrNil(draft.object),
            sourcePageLabel: trimmedOrNil(draft.sourcePageLabel),
            claimType: Components.Schemas.ClaimType(rawValue: draft.claimType),
            epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: draft.epistemicStatus)
        )
    }

    /// The per-sentence editor: a subject entity ID (never a name made up on the client, the
    /// engine derives it) sent only when the picker changed it, plus the date fields.
    static func inline(_ draft: ClaimDraft, originalSubjectEntityId: String?) -> ClaimPatchFields {
        ClaimPatchFields(
            subjectEntityId: draft.subjectEntityId != originalSubjectEntityId ? draft.subjectEntityId : nil,
            predicateVerb: trimmedOrNil(draft.predicate),
            objectPhrase: trimmedOrNil(draft.object),
            sourcePageLabel: trimmedOrNil(draft.sourcePageLabel),
            claimType: Components.Schemas.ClaimType(rawValue: draft.claimType),
            epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: draft.epistemicStatus),
            timeStart: trimmedOrNil(draft.timeStart),
            timeEnd: trimmedOrNil(draft.timeEnd),
            timePrecision: trimmedOrNil(draft.timePrecision)
        )
    }
}

/// What a claim editor is holding while a person types: ONE value in place of the ten loose
/// `@State` strings each editor used to carry (#5092). Both editors open on the same claim with the
/// same defaults, so those live here once; each editor uses the fields it shows and the factories
/// above decide what is sent. `subject` is the display NAME (typed in the sheet, shown by the picker
/// in the inline editor); only the sheet sends it.
struct ClaimDraft: Equatable {
    var text: String
    var subject: String
    var subjectEntityId: String?
    var predicate: String
    var object: String
    var sourcePageLabel: String
    var claimType: String
    var epistemicStatus: String
    var timeStart: String
    var timeEnd: String
    var timePrecision: String
}

/// The draft an editor opens on. In an extension so the memberwise initialiser stays available to
/// tests, which build drafts value by value.
extension ClaimDraft {
    init(claim: Components.Schemas.KnowledgeClaim) {
        text = claim.text
        subject = claim.subjectCanonical ?? ""
        subjectEntityId = claim.subjectEntityId
        predicate = claim.predicateVerb ?? ""
        object = claim.objectPhrase ?? ""
        sourcePageLabel = claim.sourcePageLabel ?? ""
        claimType = claim.claimType?.rawValue ?? "claim"
        epistemicStatus = claim.epistemicStatus?.rawValue ?? "tentative"
        timeStart = claim.timeStart ?? ""
        timeEnd = claim.timeEnd ?? ""
        timePrecision = claim.timePrecision ?? ""
    }
}

extension ClaimStore {
    /// The editors' one save call: the audited `claim.patch` via `patch(claimId:...)`, splicing
    /// the one returned row. Returns the SERVER's claim, never the stale one the editor opened.
    @discardableResult
    func patch(claimId: String, fields: ClaimPatchFields) async throws -> Components.Schemas.KnowledgeClaim {
        try await patch(
            claimId: claimId,
            text: fields.text,
            subjectCanonical: fields.subjectCanonical,
            subjectEntityId: fields.subjectEntityId,
            predicateVerb: fields.predicateVerb,
            objectPhrase: fields.objectPhrase,
            sourcePageLabel: fields.sourcePageLabel,
            claimType: fields.claimType,
            epistemicStatus: fields.epistemicStatus,
            timeStart: fields.timeStart,
            timeEnd: fields.timeEnd,
            timePrecision: fields.timePrecision
        )
    }
}
