import Foundation
import Observation

/// Cross-view focus for knowledge-graph interactions.
///
/// This is intentionally separate from document/sidebar selection. KG row,
/// card, and graph clicks update this state so the WebKit graph and source
/// preview can focus the same entity/claim without moving the library tree.
@MainActor
@Observable
final class KGFocusState {
    static let shared = KGFocusState()

    var focusedEntityId: String?
    var focusedClaimId: String?
    var sourceDocumentId: String?
    var sourcePageLabel: String?

    var focusKey: String {
        [
            focusedEntityId ?? "",
            focusedClaimId ?? "",
            sourceDocumentId ?? "",
            sourcePageLabel ?? ""
        ].joined(separator: "|")
    }

    func focusEntity(
        entityId: String?,
        sourceDocumentId: String? = nil,
        sourcePageLabel: String? = nil
    ) {
        focusedEntityId = entityId
        focusedClaimId = nil
        self.sourceDocumentId = sourceDocumentId
        self.sourcePageLabel = sourcePageLabel
    }

    func focusClaim(
        claimId: String?,
        entityId: String? = nil,
        sourceDocumentId: String? = nil,
        sourcePageLabel: String? = nil
    ) {
        focusedClaimId = claimId
        focusedEntityId = entityId
        self.sourceDocumentId = sourceDocumentId
        self.sourcePageLabel = sourcePageLabel
    }

    func clear() {
        focusedEntityId = nil
        focusedClaimId = nil
        sourceDocumentId = nil
        sourcePageLabel = nil
    }
}
