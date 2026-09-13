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
        Self.showsPreviewPane(viewMode: viewMode, layoutMode: currentLayoutMode)
    }

    /// Whether the preview pane shows, given the view mode and layout mode.
    /// Extracted pure so the policy is unit-testable off-view (spec:
    /// panes-magnifiers-workspaces — the "Entities view takes over" fix).
    ///
    /// Selection KIND no longer changes this. An earlier `isEntityLibrarySelection`
    /// special-case returned `false` here for the Entities collection, so entities
    /// alone lost the preview and reflowed to a full-width takeover
    /// (`centerContentRouting`'s `!showsPreviewPane` branch), while Claims — never
    /// special-cased — kept the two-pane layout. That divergence violated the
    /// stable-panes policy (#1452/#4525: a folder keeps the same panes as a file,
    /// so selecting different items never reflows the window). Entity, claim and
    /// folder `.library` selections now all keep the same panes — the parity the
    /// CD asked for (2026-09-13, "entities takes over, claims have it").
    static func showsPreviewPane(viewMode: AppViewMode, layoutMode: LayoutMode) -> Bool {
        guard layoutMode != .none else { return false }
        switch viewMode {
        case .library, .chat:
            // Chat also keeps the panes (Daniel 2026-08-12: chat must never
            // collapse the workspace).
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
