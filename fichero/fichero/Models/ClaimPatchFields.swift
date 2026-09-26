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
    static func sheet(
        text: String, subject: String, predicate: String, object: String, sourcePageLabel: String,
        claimType: String, epistemicStatus: String
    ) -> ClaimPatchFields {
        ClaimPatchFields(
            text: text.trimmingCharacters(in: .whitespacesAndNewlines),
            subjectCanonical: trimmedOrNil(subject),
            predicateVerb: trimmedOrNil(predicate),
            objectPhrase: trimmedOrNil(object),
            sourcePageLabel: trimmedOrNil(sourcePageLabel),
            claimType: Components.Schemas.ClaimType(rawValue: claimType),
            epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: epistemicStatus)
        )
    }

    /// The per-sentence editor: a subject entity ID (never a name made up on the client, the
    /// engine derives it) sent only when the picker changed it, plus the date fields.
    static func inline(
        subjectEntityId: String?, originalSubjectEntityId: String?, predicate: String, object: String,
        sourcePageLabel: String, claimType: String, epistemicStatus: String,
        timeStart: String, timeEnd: String, timePrecision: String
    ) -> ClaimPatchFields {
        ClaimPatchFields(
            subjectEntityId: subjectEntityId != originalSubjectEntityId ? subjectEntityId : nil,
            predicateVerb: trimmedOrNil(predicate),
            objectPhrase: trimmedOrNil(object),
            sourcePageLabel: trimmedOrNil(sourcePageLabel),
            claimType: Components.Schemas.ClaimType(rawValue: claimType),
            epistemicStatus: Components.Schemas.EpistemicStatus(rawValue: epistemicStatus),
            timeStart: trimmedOrNil(timeStart),
            timeEnd: trimmedOrNil(timeEnd),
            timePrecision: trimmedOrNil(timePrecision)
        )
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
