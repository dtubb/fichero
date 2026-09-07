import SwiftUI

// MARK: - Navigation History

extension ContentView {
    func recordNavigationEntry() {
        guard !isRestoringNavigationHistory else { return }
        let serialized = Self.serializeViewMode(viewMode)
        navigationHistory.push(AppNavigationHistory.Entry(
            viewType: serialized.type,
            viewItemId: serialized.id,
            selectedSidebarItemId: sidebarSelectionState.selectedItemId,
            browserSelection: browserSelection,
            detailDocumentId: detailDocument?.id,
            // Capture the live transient-search query so a later Back returns
            // to these results (#4106) rather than dropping the user into the
            // browsed folder with no query.
            searchQuery: activeSearchQuery
        ))
    }

    func navigateBack() {
        guard let entry = navigationHistory.goBack() else { return }
        applyNavigationEntry(entry)
    }

    func navigateForward() {
        guard let entry = navigationHistory.goForward() else { return }
        applyNavigationEntry(entry)
    }

    @MainActor
    func applyNavigationEntry(_ entry: AppNavigationHistory.Entry) {
        isRestoringNavigationHistory = true
        sidebarMode = sidebarMode(for: entry.viewType)
        viewMode = restoreViewMode(type: entry.viewType, itemId: entry.viewItemId)
        sidebarSelectionState.selectedItemId = entry.selectedSidebarItemId
        browserSelection = entry.browserSelection
        storedViewModeType = entry.viewType
        storedViewModeItemId = entry.viewItemId
        if let encoded = try? JSONEncoder().encode(entry.browserSelection) {
            browserSelectionData = encoded
        }

        // Restore the transient search this entry belonged to, or leave one we
        // are stepping away from (#4106). Done BEFORE the detail-document
        // restore because re-running the search resolves its own result rows;
        // `restoreTransientSearchFromHistory` owns the restoring flag across
        // its async fetch so nothing records a spurious entry mid-restore.
        if let query = entry.searchQuery, query != activeSearchQuery {
            restoreTransientSearchFromHistory(query)
            return
        }
        if entry.searchQuery == nil, activeSearchQuery != nil {
            clearTransientSearch()
        }

        if let detailDocumentId = entry.detailDocumentId {
            applyHistoryDetailDocument(detailDocumentId)
        } else {
            detailDocument = nil
            isRestoringNavigationHistory = false
        }
    }

    /// Re-run the transient search a history entry captured, holding the
    /// restoring flag until the async result resolution completes so the
    /// selection/detail writes it makes do not record new history entries
    /// (which would truncate the forward branch). Mirrors the async detail
    /// restore in `applyHistoryDetailDocument`.
    @MainActor
    private func restoreTransientSearchFromHistory(_ query: String) {
        showSearchField = true
        toolbarSearchText = query
        activeSearchQuery = query
        libraryToolbarState.searchIsActive = true
        libraryToolbarState.userChoseSortDuringSearch = false
        transientSearchLimit = Self.transientSearchPageSize
        Task { @MainActor in
            await runTransientSearch(query)
            isRestoringNavigationHistory = false
        }
    }

    private func applyHistoryDetailDocument(_ detailDocumentId: String) {
        if let doc = documentStore.currentDocuments.first(where: { $0.id == detailDocumentId })
            ?? documentStore.collections.first(where: { $0.id == detailDocumentId }) {
            detailDocument = doc
            isRestoringNavigationHistory = false
        } else {
            detailDocument = nil
            Task { @MainActor in
                let fetched = try? await documentStore.documentService.getDocument(detailDocumentId)
                isRestoringNavigationHistory = true
                detailDocument = fetched
                isRestoringNavigationHistory = false
            }
        }
    }

    func sidebarMode(for viewType: String) -> SidebarMode {
        switch viewType {
        case "chat":
            return .chat
        case "workflow", "chain":
            return .workflows
        case "automation", "schedule", "trigger":
            return .automation
        case "activity", "batch", "batches":
            return .activity
        default:
            return .library
        }
    }
}
