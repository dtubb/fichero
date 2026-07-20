import Observation
import SwiftUI

// MARK: - View Helpers

extension View {
    /// Conditionally shows a view based on a feature flag
    @ViewBuilder
    func featureEnabled(_ isEnabled: Bool) -> some View {
        if isEnabled {
            self
        }
    }
}

// MARK: - ClaimFocusState

/// Observable state for bidirectional claim highlighting across PDF, Content, and Inspector panes.
@MainActor
@Observable
class ClaimFocusState {
    static let shared = ClaimFocusState()

    var selectedClaimId: String?
    var selectedClaimText: String?
    var selectedClaimSourceDocumentId: String?
    var selectedClaimPageLabel: String?
    var selectedClaimCharStart: Int?
    var selectedClaimCharEnd: Int?

    func selectClaim(
        claimId: String,
        claimText: String? = nil,
        sourceDocumentId: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        selectedClaimId = claimId
        selectedClaimText = claimText
        selectedClaimSourceDocumentId = sourceDocumentId
        selectedClaimPageLabel = pageLabel
        selectedClaimCharStart = charStart
        selectedClaimCharEnd = charEnd
        NotificationCenter.default.post(name: .claimFocusChanged, object: self)
    }

    func clearSelection() {
        selectedClaimId = nil
        selectedClaimText = nil
        selectedClaimSourceDocumentId = nil
        selectedClaimPageLabel = nil
        selectedClaimCharStart = nil
        selectedClaimCharEnd = nil
        NotificationCenter.default.post(name: .claimFocusChanged, object: self)
    }

    func isClaimSelected(_ claimId: String) -> Bool { selectedClaimId == claimId }

    /// Synchronize claim focus across all panes (PDF, Content, Inspector)
    /// This method ensures that when a claim is selected in one pane,
    /// it's properly synced to all other panes for a unified experience
    func syncClaimFocus(
        to documentId: String,
        claimId: String,
        claimText: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        // Select the claim across all panes
        selectClaim(
            claimId: claimId,
            claimText: claimText,
            sourceDocumentId: documentId,
            pageLabel: pageLabel,
            charStart: charStart,
            charEnd: charEnd
        )
    }
}

extension Notification.Name {
    static let claimFocusChanged = Notification.Name("claimFocusChanged")
}
