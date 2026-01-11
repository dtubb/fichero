import SwiftUI

// MARK: - Sidebar Bottom Toolbar

/// Compact bottom toolbar for sidebar with common actions.
///
/// Modeled after macOS Preview/Finder bottom toolbars with small, icon-only buttons.
struct SidebarBottomToolbar: View {
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createFolder: () -> Void
    let importFiles: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            // New item menu (dropdown)
            Menu {
                Button(action: createSearch) {
                    Label("New Search", systemImage: "magnifyingglass")
                }
                Button(action: createChat) {
                    Label("New Chat", systemImage: "bubble.left.and.bubble.right")
                }
                Button(action: createWorkflow) {
                    Label("New Workflow", systemImage: "arrow.triangle.branch")
                }

                Divider()

                Button(action: createFolder) {
                    Label("New Folder", systemImage: "folder.badge.plus")
                }
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 11))
                    .frame(width: 20, height: 20)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("New Item")

            Spacer()

            // Import button
            Button(action: importFiles) {
                Image(systemName: "square.and.arrow.down")
                    .font(.system(size: 11))
                    .frame(width: 20, height: 20)
            }
            .buttonStyle(.borderless)
            .help("Import Files (⌘I)")
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(.ultraThinMaterial)
        .frame(height: 28)
    }
}

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

/// Configuration for sidebar toolbar
struct SidebarToolbarConfig {
    let createFolder: () -> Void
    let importFiles: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
}

extension View {
    /// Adds sidebar toolbar with create menu and import button.
    func sidebarToolbar(config: SidebarToolbarConfig) -> some View {
        self.toolbar {
            ToolbarItem(placement: .automatic) {
                Menu {
                    Button(action: config.createFolder) {
                        Label("New Folder", systemImage: "folder.badge.plus")
                    }

                    Divider()

                    Button(action: config.createSearch) {
                        Label("New Search", systemImage: "magnifyingglass")
                    }

                    Button(action: config.createChat) {
                        Label("New Chat", systemImage: "bubble.left.and.bubble.right")
                    }

                    Button(action: config.createWorkflow) {
                        Label("New Workflow", systemImage: "arrow.triangle.branch")
                    }
                } label: {
                    Label("New", systemImage: "plus")
                }
                .help("New Item")
            }

            ToolbarItem(placement: .automatic) {
                Button(action: config.importFiles) {
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

/// Configuration for sidebar focused values
struct SidebarFocusedValuesConfig {
    let selectedItem: SidebarItem?
    let createFolder: () -> Void
    let importFiles: () -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
}

extension View {
    /// Publishes sidebar actions and selection info to the focus system for menu bar commands.
    func sidebarFocusedValues(config: SidebarFocusedValuesConfig) -> some View {
        self
            .focusedValue(\.sidebarActions, SidebarActions(
                createFolder: config.createFolder,
                importFiles: config.importFiles,
                renameItem: config.renameItem,
                deleteItem: config.deleteItem,
                createSearch: config.createSearch,
                createChat: config.createChat,
                createWorkflow: config.createWorkflow
            ))
            .focusedValue(\.sidebarSelectionInfo, SidebarSelectionInfo(
                selectedItem: config.selectedItem,
                canRename: config.selectedItem?.itemType.canBeRenamed ?? false,
                canDelete: config.selectedItem?.itemType.canBeDeleted ?? false
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

// MARK: - New Folder Dialog

extension View {
    /// Adds new folder creation alert dialog.
    func sidebarNewFolderDialog(
        sidebarState: SidebarState,
        createFolder: @escaping (String) async -> Void
    ) -> some View {
        self.modifier(SidebarNewFolderDialogModifier(
            sidebarState: sidebarState,
            createFolder: createFolder
        ))
    }
}

private struct SidebarNewFolderDialogModifier: ViewModifier {
    @ObservedObject var sidebarState: SidebarState
    let createFolder: (String) async -> Void

    func body(content: Content) -> some View {
        content
            .alert(
                "New Folder",
                isPresented: $sidebarState.showingNewFolderDialog,
                actions: {
                    TextField("Folder Name", text: $sidebarState.newFolderName)
                    Button("Create") {
                        let folderName = sidebarState.newFolderName.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !folderName.isEmpty else { return }
                        Task {
                            await createFolder(folderName)
                            sidebarState.resetFolderCreationState()
                        }
                    }
                    .keyboardShortcut(.defaultAction)
                    .disabled(sidebarState.newFolderName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button("Cancel", role: .cancel) {
                        sidebarState.resetFolderCreationState()
                    }
                },
                message: {
                    Text("Enter a name for the new folder.")
                }
            )
            .alert("Folder Creation Failed", isPresented: .constant(sidebarState.newFolderErrorMessage != nil)) {
                Button("OK", role: .cancel) {
                    sidebarState.newFolderErrorMessage = nil
                }
            } message: {
                Text(sidebarState.newFolderErrorMessage ?? "Unknown error")
            }
    }
}

// MARK: - File Import

extension View {
    /// Adds file importer for importing files into the library.
    func sidebarFileImporter(
        isPresented: Binding<Bool>,
        importFiles: @escaping ([URL]) async -> Void
    ) -> some View {
        self.fileImporter(
            isPresented: isPresented,
            allowedContentTypes: [.item, .folder],
            allowsMultipleSelection: true
        ) { result in
            switch result {
            case .success(let urls):
                Task {
                    await importFiles(urls)
                }
            case .failure(let error):
                // Log but don't show error - user cancelled or other benign issue
                print("File import cancelled or failed: \(error.localizedDescription)")
            }
        }
    }
}
