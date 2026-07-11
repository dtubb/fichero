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

    /// A request to reveal an entity in the full Knowledge Graph force graph
    /// (#3452). Inspector "Show in Graph" affordances call ``requestGraphReveal``;
    /// ContentView watches ``graphRevealRequestToken`` and switches to the
    /// Knowledge Graph mode focused on ``focusedEntityId``. The token makes
    /// repeat reveals of the same entity still fire.
    private(set) var graphRevealRequestToken = 0

    /// Focus `entityId` and ask the shell to switch into the force-graph view.
    func requestGraphReveal(entityId: String) {
        focusEntity(entityId: entityId)
        graphRevealRequestToken &+= 1
    }

    func focusEntity(
        entityId: String?,
        sourceDocumentId: String? = nil,
        sourcePageLabel: String? = nil
    ) {
        guard focusedEntityId != entityId
            || focusedClaimId != nil
            || self.sourceDocumentId != sourceDocumentId
            || self.sourcePageLabel != sourcePageLabel
        else { return }
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
        guard focusedClaimId != claimId
            || focusedEntityId != entityId
            || self.sourceDocumentId != sourceDocumentId
            || self.sourcePageLabel != sourcePageLabel
        else { return }
        focusedClaimId = claimId
        focusedEntityId = entityId
        self.sourceDocumentId = sourceDocumentId
        self.sourcePageLabel = sourcePageLabel
    }

    func clear() {
        guard focusedEntityId != nil
            || focusedClaimId != nil
            || sourceDocumentId != nil
            || sourcePageLabel != nil
        else { return }
        focusedEntityId = nil
        focusedClaimId = nil
        sourceDocumentId = nil
        sourcePageLabel = nil
    }

    /// Compact push/pop bridge (#3011). Pushing an entity detail focuses it;
    /// popping back to the list (a `nil` leaf) clears KG focus so the list
    /// returns unfocused. Mirrors the compact entity NavigationStack's
    /// `navigationDestination(item:)` lifecycle.
    func syncPushedEntity(_ entityId: String?) {
        if let entityId {
            focusEntity(entityId: entityId)
        } else {
            clear()
        }
    }
}
