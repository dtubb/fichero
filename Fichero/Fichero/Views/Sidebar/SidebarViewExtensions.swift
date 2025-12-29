import SwiftUI

// MARK: - View Extensions (Apple's recommended pattern over ViewModifiers)

extension View {
    /// Applies standard sidebar styling (list style and minimum width).
    func sidebarStyle() -> some View {
        self
            .listStyle(.sidebar)
            .frame(minWidth: SidebarConstants.minimumWidth)
    }
}

extension View {
    /// Adds sidebar toolbar with actions for creating, importing, renaming, and deleting items.
    func sidebarToolbar(
        selectedItem: SidebarItem?,
        createFolder: @escaping () -> Void,
        importFiles: @escaping () -> Void,
        renameItem: @escaping () -> Void,
        deleteItem: @escaping () -> Void
    ) -> some View {
        self.toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button(action: createFolder) {
                    Image(systemName: "folder.badge.plus")
                }
                .help("New Folder")

                Button(action: importFiles) {
                    Image(systemName: "square.and.arrow.down")
                }
                .help("Import Files")

                Button(action: renameItem) {
                    Image(systemName: "pencil")
                }
                .help("Rename")
                .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeRenamed ?? false))

                Button(action: deleteItem) {
                    Image(systemName: "trash")
                }
                .help("Delete")
                .disabled(selectedItem == nil || !(selectedItem?.itemType.canBeDeleted ?? false))
            }
        }
    }
}

extension View {
    /// Monitors data sources and rebuilds sidebar caches when they change.
    func sidebarCacheMonitoring(
        rebuildCaches: @escaping () -> Void,
        documentStore: DocumentStore,
        savedSearchService: SavedSearchService,
        conversationService: ConversationService,
        workflowStore: WorkflowStore,
        selectedItem: SidebarItem?,
        handleSelection: @escaping (SidebarItem?) -> Void
    ) -> some View {
        self
            .task {
                // Build initial caches when view appears
                rebuildCaches()
            }
            .onChange(of: documentStore.collections) { _, _ in
                rebuildCaches()
            }
            .onChange(of: savedSearchService.savedSearches) { _, _ in
                rebuildCaches()
            }
            .onChange(of: conversationService.conversations) { _, _ in
                rebuildCaches()
            }
            .onChange(of: workflowStore.workflows) { _, _ in
                rebuildCaches()
            }
            .onChange(of: selectedItem) { _, newItem in
                handleSelection(newItem)
            }
    }
}

extension View {
    /// Publishes sidebar actions and selection info to the focus system for menu bar commands.
    func sidebarFocusedValues(
        selectedItem: SidebarItem?,
        createFolder: @escaping () -> Void,
        renameItem: @escaping () -> Void,
        deleteItem: @escaping () -> Void
    ) -> some View {
        self
            .focusedValue(\.sidebarActions, SidebarActions(
                createFolder: createFolder,
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
