import SwiftUI

// MARK: - ContentView Claim Actions

extension ContentView {

    // MARK: - Claim Selection Sync

    /// Handle claim selection from any pane and sync to all other panes
    func syncClaimSelection(
        claimId: String,
        claimText: String? = nil,
        sourceDocumentId: String? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        // Only sync if the feature is enabled
        guard FeatureManager.shared.isClaimHighlightSyncEnabled else { return }

        // Update the global claim focus state
        claimFocusState.selectClaim(
            claimId: claimId,
            claimText: claimText,
            sourceDocumentId: sourceDocumentId,
            pageLabel: pageLabel,
            charStart: charStart,
            charEnd: charEnd
        )

        // If the claim has a source document, select it in the grid
        if let sourceDocId = sourceDocumentId, sourceDocId != inspectorDocument?.id {
            selectDocument(withId: sourceDocId)
        }

        // If the claim has page information, scroll to it in the PDF
        if let pageLabel = pageLabel {
            scrollToPage(pageLabel: pageLabel)
        }
    }

    /// Clear the claim selection
    func clearClaimSelection() {
        guard FeatureManager.shared.isClaimHighlightSyncEnabled else { return }
        claimFocusState.clearSelection()
    }

    func handleKGFocusChanged() {
        guard let sourceDocId = kgFocusState.sourceDocumentId,
              !sourceDocId.isEmpty else { return }
        Task { @MainActor in
            await focusKGSourcePreview(sourceDocId)
            var info: [String: Any] = ["documentId": sourceDocId]
            if let claimId = kgFocusState.focusedClaimId, !claimId.isEmpty {
                info["claimId"] = claimId
            }
            if let pageLabel = kgFocusState.sourcePageLabel, !pageLabel.isEmpty {
                info["pageLabel"] = pageLabel
            }
            NotificationCenter.default.post(
                name: .ficheroNavigateToPage,
                object: nil,
                userInfo: info
            )
        }
    }

    var showsPreviewPane: Bool {
        guard currentLayoutMode != .none else { return false }
        switch viewMode {
        case .library:
            if isEntityLibrarySelection {
                return false
            }
            // Stable layout (default): a folder keeps the same panes as a file,
            // so selecting different items never reflows the window (#1452). The
            // legacy behaviour — folder collapses the preview so the grid takes
            // full width (#712) — is now opt-in via layoutFollowsSelection.
            if layoutFollowsSelection, let doc = inspectorDocument, doc.docType == .folder {
                return false
            }
            return true
        default:
            return false
        }
    }

    // MARK: - Document Change Handler

    @MainActor
    func handleDocumentChange(_ change: DocumentChange) {
        switch change {
        case .collectionsUpdated:
            break

        case .collectionSelected(let collection):
            sidebarSelectionState.selectedItemId = "doc:\(collection.id)"

        case .documentsUpdated:
            break

        case .documentDeleted(let document):
            browserSelection.remove(document.id)
            if detailDocument?.id == document.id {
                detailDocument = nil
            }

        case .documentCreated:
            break
        }
    }
}
