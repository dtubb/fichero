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

// MARK: - Cross-window handoff (#4850)

/// `KGFocusState` is PER-WINDOW (`ContentView` owns one, `@State var
/// kgFocusState = KGFocusState()`) since #4850: a single process-wide
/// `.shared` instance meant a click in one window's Entities table also drove
/// a DIFFERENT window's Inspector — which resolves entities against ITS OWN
/// library — against the wrong one, surfacing as a false "Entity Unavailable".
///
/// "Open in New Window/Tab" (#1685) still needs a one-shot handoff: the new
/// window's own `KGFocusState` does not exist until the window finishes
/// opening, so there is nowhere per-window to write the initial focus to yet.
/// `.shared` is repurposed as EXACTLY that — a single-value mailbox, written
/// once by the opener and consumed once by the new window's first appearance,
/// never read by anything else. A THIRD window opened later must never
/// inherit a stale handoff, so consuming always clears it.
extension KGFocusState {
    /// Stash the focus a newly-opened window should start with. Call
    /// immediately before `WindowOpener.open(...)`.
    static func handOffToNewWindow(
        entityId: String?,
        claimId: String?,
        sourceDocumentId: String?,
        sourcePageLabel: String?
    ) {
        shared.focusedEntityId = entityId
        shared.focusedClaimId = claimId
        shared.sourceDocumentId = sourceDocumentId
        shared.sourcePageLabel = sourcePageLabel
    }

    /// Read and clear a pending hand-off, if any. Call once, from the
    /// receiving window's own `KGFocusState` instance (never from `.shared`
    /// itself, which would be a no-op self-copy-then-clear).
    func consumePendingHandoff() {
        guard self !== Self.shared else { return }
        guard Self.shared.focusedEntityId != nil || Self.shared.focusedClaimId != nil else { return }
        focusedEntityId = Self.shared.focusedEntityId
        focusedClaimId = Self.shared.focusedClaimId
        sourceDocumentId = Self.shared.sourceDocumentId
        sourcePageLabel = Self.shared.sourcePageLabel
        Self.shared.clear()
    }
}
