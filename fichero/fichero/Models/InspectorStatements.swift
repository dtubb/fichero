import Foundation

/// The Inspector's statements (`build-notes-inspector.md` 5.7, second half; `source.statement.on-segment`,
/// `both-ways`): what is SAID about this segment -- the claims whose anchor, or a supporting source's,
/// names it, and the entities it mentions -- each opening its claim or entity in the knowledge views.
/// Read-only here. Pure: the words live where a test can reach them.
enum InspectorStatements {
    struct Claim: Equatable, Identifiable {
        let id: String
        let text: String
        let curationState: String
        let confidence: Double
        /// "anchor" (the claim's own anchor names the segment) or "support" (a supporting source does).
        let via: String
        var excerpt: String?
    }

    struct Mention: Equatable, Identifiable {
        let id: String
        let name: String
        let entityType: String
        var excerpt: String?
    }

    struct Answer: Equatable {
        var claims: [Claim] = []
        var mentions: [Mention] = []
    }

    struct Row: Equatable, Identifiable {
        /// The claim or entity id the row opens.
        let targetId: String
        let isClaim: Bool
        let title: String
        /// "unreviewed · confidence 50% · from this segment's own anchor · “ܐܒܪܗܡ ܐܘܠܕ”".
        let detail: String
        var id: String { (isClaim ? "claim:" : "entity:") + targetId }
    }

    static func rows(_ answer: Answer) -> [Row] {
        let claims = answer.claims.map { claim in
            var parts = [claim.curationState.replacingOccurrences(of: "_", with: " "),
                         "confidence \(Int((claim.confidence * 100).rounded()))%",
                         claim.via == "anchor" ? "anchored here" : "a supporting source is here"]
            if let excerpt = claim.excerpt, !excerpt.isEmpty { parts.append("“\(excerpt)”") }
            return Row(targetId: claim.id, isClaim: true, title: claim.text, detail: parts.joined(separator: " · "))
        }
        let mentions = answer.mentions.map { mention in
            var parts = [mention.entityType.replacingOccurrences(of: "_", with: " ")]
            if let excerpt = mention.excerpt, !excerpt.isEmpty { parts.append("“\(excerpt)”") }
            return Row(targetId: mention.id, isClaim: false, title: mention.name, detail: parts.joined(separator: " · "))
        }
        return claims + mentions
    }
}
