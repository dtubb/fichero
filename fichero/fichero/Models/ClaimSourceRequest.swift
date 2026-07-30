import FicheroAPIClient
import Foundation

/// Turns a claim into a request on the EXISTING source-navigation cursor
/// (#4393 part 2).
///
/// No new addressing scheme. `ClaimSourceNavigationRequest` already carries
/// `charStart`, `charEnd`, `bbox`, `pageIndex` and `pageLabel`, and already has
/// four producers — annotations, artifacts, the source outline, and the KG web
/// pane. The claims list was simply never one of them, so a claim was the only
/// thing in the inspector you could not get back to the page from.
///
/// That is the same pattern as the rest of today: a complete mechanism with a
/// missing end. Here the end that was missing is the producer, not the
/// consumer.
///
/// **Never approximate a location.** A claim with no recorded span navigates to
/// the page and says the region is unknown. A confidently wrong highlight over
/// a manuscript asserts that a word appears somewhere it does not — worse than
/// no highlight, because the reader has no way to discover it is wrong.
enum ClaimSourceRequest {

    /// What the caller can promise the user about where this claim came from.
    enum Precision: Equatable {
        /// A character span was recorded — reveal and highlight the passage.
        case span
        /// A source region was recorded — reveal and highlight the region.
        case region
        /// Only a page. Navigate there; do not draw a highlight.
        case pageOnly
        /// Not even a document. There is nowhere honest to go.
        case unknown

        /// Whether a highlight may be drawn at all. The rule the issue turns
        /// on: no span, no highlight.
        var drawsHighlight: Bool { self == .span || self == .region }

        /// What the UI tells the user when it cannot be exact.
        var caveat: String? {
            switch self {
            case .span, .region: return nil
            case .pageOnly: return "Opened the page — the exact passage was not recorded"
            case .unknown: return "No source recorded for this claim"
            }
        }
    }

    /// How precisely this claim's origin is known.
    ///
    /// Checked in order of what can actually be shown: a character span is the
    /// most exact, a bbox next, then the page. A span of zero length is treated
    /// as absent — it addresses no text, and highlighting it would put a caret
    /// somewhere arbitrary.
    static func precision(for claim: Components.Schemas.KnowledgeClaim) -> Precision {
        guard let documentId = claim.sourceDocumentId,
              !documentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return .unknown
        }
        if let start = claim.sourceCharStart, let end = claim.sourceCharEnd, end > start {
            return .span
        }
        if let bbox = claim.sourceBbox, bbox.count == 4 {
            return .region
        }
        return .pageOnly
    }

    /// The request to hand to `ClaimSourceNavigationState`, or `nil` when there
    /// is nowhere honest to navigate.
    ///
    /// Span and region fields are carried ONLY at the precision that earned
    /// them, so a downstream consumer cannot accidentally highlight from a
    /// value this function did not vouch for.
    static func request(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> ClaimSourceNavigationRequest? {
        let precision = precision(for: claim)
        guard precision != .unknown, let documentId = claim.sourceDocumentId else { return nil }

        var request = ClaimSourceNavigationRequest(documentId: documentId)
        request.claimId = claim.id
        request.claimText = claim.text
        request.pageLabel = claim.sourcePageLabel
        request.destination = .reader

        switch precision {
        case .span:
            request.charStart = claim.sourceCharStart
            request.charEnd = claim.sourceCharEnd
        case .region:
            request.bbox = claim.sourceBbox
        case .pageOnly, .unknown:
            break
        }
        return request
    }
}
