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
            detailDocumentId: detailDocument?.id
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

        if let detailDocumentId = entry.detailDocumentId {
            applyHistoryDetailDocument(detailDocumentId)
        } else {
            detailDocument = nil
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
