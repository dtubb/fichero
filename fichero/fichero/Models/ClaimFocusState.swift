import Foundation
import SwiftUI

/// Observable object that tracks which claim is currently focused across
/// the three panes of the document view (PDF, Content, Inspector).
///
/// This enables bidirectional sync - when a user clicks a claim in any
/// pane, it should highlight the same claim in all other panes.
@MainActor
class ClaimFocusState: ObservableObject {
    /// Shared instance for global access
    static let shared = ClaimFocusState()

    /// The ID of the currently selected claim, or nil if no claim is selected
    @Published var selectedClaimId: String?

    /// The document ID of the currently selected document
    @Published var selectedDocumentId: String?

    /// Whether a claim is currently selected (for quick checks)
    var isClaimSelected: Bool {
        selectedClaimId != nil
    }

    /// Check if a specific claim is currently selected
    /// - Parameter claimId: The ID of the claim to check
    /// - Returns: True if the claim is currently selected, false otherwise
    func isClaimSelected(_ claimId: String) -> Bool {
        selectedClaimId == claimId
    }

    /// Select a claim by ID
    /// - Parameter claimId: The ID of the claim to select
    func selectClaim(_ claimId: String) {
        selectedClaimId = claimId
    }

    /// Clear the current claim selection
    func clearSelection() {
        selectedClaimId = nil
    }

    /// Update the selected document
    /// - Parameter documentId: The ID of the document to select
    func selectDocument(_ documentId: String) {
        selectedDocumentId = documentId
        // Clear claim selection when switching documents
        clearSelection()
    }

    /// Clear the current document and claim selections
    func clearDocumentAndSelection() {
        selectedDocumentId = nil
        clearSelection()
    }
}
