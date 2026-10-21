import Foundation

/// A read that is not trusted (`ReadFlagInfo` on the engine's page Document, #6003): `kind` in a word, `reason` in a
/// sentence. The Inspector's page section and the page's row say it in the same words (`note`).
struct ReadFlag: Codable, Hashable, Sendable {
    let kind: String
    let reason: String
    /// The flagged read's own measure, kept as the engine sends it.
    let measure: [String: AnyCodable]?

    /// "Needs re-reading: <reason>" for the repair's kind; any other kind shows only its reason, never the kind's id.
    var note: String {
        guard kind == "needs-re-reading" else { return reason }
        return reason.isEmpty ? "Needs re-reading" : "Needs re-reading: " + reason
    }
}
