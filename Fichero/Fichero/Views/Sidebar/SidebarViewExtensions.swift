import SwiftUI

// MARK: - View Extensions (Apple's recommended pattern over ViewModifiers)

extension View {
    /// Applies standard sidebar styling (list style, transparency, and minimum width).
    func sidebarStyle() -> some View {
        self
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)  // Transparent sidebar background
            .frame(minWidth: SidebarConstants.minimumWidth)
    }
}

extension View {
    /// Adds sidebar toolbar with minimal actions.
    func sidebarToolbar(
        selectedItem: SidebarItem?,
        createFolder: @escaping () -> Void,
        importFiles: @escaping () -> Void,
        renameItem: @escaping () -> Void,
        deleteItem: @escaping () -> Void
    ) -> some View {
        self.toolbar {
            ToolbarItem(placement: .automatic) {
                Button(action: createFolder) {
                    Image(systemName: "folder.badge.plus")
                }
                .help("New Folder (⌘⇧N)")
            }

            ToolbarItem(placement: .automatic) {
                Button(action: importFiles) {
                    Image(systemName: "square.and.arrow.down")
                }
                .help("Import Files or Folders (⌘I)")
            }
        }
    }
}

/// Configuration for sidebar cache monitoring
struct SidebarCacheMonitoringConfig {
    let rebuildCaches: () -> Void
    let documentStore: DocumentStore
    let savedSearchService: SavedSearchService
    let conversationService: ConversationService
    let workflowStore: WorkflowStore
    let selectedItem: SidebarItem?
    let handleSelection: (SidebarItem?) -> Void
}

extension View {
    /// Monitors data sources and rebuilds sidebar caches when they change.
    func sidebarCacheMonitoring(
        config: SidebarCacheMonitoringConfig
    ) -> some View {
        self
            .task {
                // Build initial caches when view appears
                config.rebuildCaches()
            }
            .onChange(of: config.documentStore.collections) { _, _ in
                config.rebuildCaches()
            }
            .onChange(of: config.savedSearchService.savedSearches) { _, _ in
                config.rebuildCaches()
            }
            .onChange(of: config.conversationService.conversations) { _, _ in
                config.rebuildCaches()
            }
            .onChange(of: config.workflowStore.workflows) { _, _ in
                config.rebuildCaches()
            }
            .onChange(of: config.selectedItem) { _, newItem in
                config.handleSelection(newItem)
            }
    }
}

extension View {
    /// Publishes sidebar actions and selection info to the focus system for menu bar commands.
    func sidebarFocusedValues(
        selectedItem: SidebarItem?,
        createFolder: @escaping () -> Void,
        importFiles: @escaping () -> Void,
        renameItem: @escaping () -> Void,
        deleteItem: @escaping () -> Void
    ) -> some View {
        self
            .focusedValue(\.sidebarActions, SidebarActions(
                createFolder: createFolder,
                importFiles: importFiles,
                renameItem: renameItem,
                deleteItem: deleteItem
            ))
            .focusedValue(\.sidebarSelectionInfo, SidebarSelectionInfo(
                selectedItem: selectedItem,
                canRename: selectedItem?.itemType.canBeRenamed ?? false,
                canDelete: selectedItem?.itemType.canBeDeleted ?? false
            ))
    }
}

// Note: This extension uses a ViewModifier wrapper because it needs @ObservedObject bindings
extension View {
    /// Adds delete confirmation and error alerts for sidebar items.
    func sidebarDeleteAlerts(
        deleteState: DeleteStateManager,
        performDelete: @escaping (SidebarItem) async -> Void
    ) -> some View {
        self.modifier(SidebarDeleteAlertsModifier(
            deleteState: deleteState,
            performDelete: performDelete
        ))
    }
}

private struct SidebarDeleteAlertsModifier: ViewModifier {
    @ObservedObject var deleteState: DeleteStateManager
    let performDelete: (SidebarItem) async -> Void

    func body(content: Content) -> some View {
        content
            .alert(
                "Delete \"\(deleteState.itemToDelete?.name ?? "")\"?",
                isPresented: $deleteState.showingDeleteConfirmation,
                presenting: deleteState.itemToDelete,
                actions: { itemToDelete in
                    Button("Delete", role: .destructive) {
                        Task {
                            await performDelete(itemToDelete)
                        }
                    }
                    .keyboardShortcut(.defaultAction)
                    Button("Cancel", role: .cancel) {
                        deleteState.cancelDelete()
                    }
                },
                message: { _ in
                    Text("This action cannot be undone.")
                }
            )
            .alert("Delete Failed", isPresented: $deleteState.showingDeleteError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(deleteState.deleteErrorMessage)
            }
    }
}
