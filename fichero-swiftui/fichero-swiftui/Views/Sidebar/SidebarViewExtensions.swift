import SwiftUI
// swiftlint:disable file_length

// MARK: - Sidebar Bottom Toolbar

/// Compact bottom toolbar for sidebar with common actions.
///
/// Modeled after macOS Preview/Finder bottom toolbars with small, icon-only buttons.
struct SidebarBottomToolbar: View {
    // Feature manager to hide buttons
    @ObservedObject var featureManager = FeatureManager.shared

    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    // Optional automation creation callbacks
    var createComparison: (() -> Void)?
    var createSchedule: (() -> Void)?
    var createTrigger: (() -> Void)?

    var body: some View {
        HStack(spacing: 0) {
            // New item menu (dropdown)
            Menu {
                if featureManager.isSearchEnabled {
                    Button(action: createSearch) {
                        Label("New Search", systemImage: "magnifyingglass")
                    }
                }

                if featureManager.isChatEnabled {
                    Button(action: createChat) {
                        Label("New Chat", systemImage: "bubble.left.and.bubble.right")
                    }
                }

                if featureManager.isWorkflowsEnabled {
                    if let createComparison = createComparison {
                        Button(action: createComparison) {
                            Label("New Comparison", systemImage: "arrow.left.arrow.right")
                        }
                    }
                    Button(action: createWorkflow) {
                        Label("New Workflow", systemImage: "arrow.triangle.branch")
                    }
                }

                if featureManager.isAutomationEnabled || featureManager.isWorkflowsEnabled {
                    Divider()
                }

                if featureManager.isAutomationEnabled {
                    if let createSchedule = createSchedule {
                        Button(action: createSchedule) {
                            Label("New Schedule", systemImage: "clock")
                        }
                    }
                    if let createTrigger = createTrigger {
                        Button(action: createTrigger) {
                            Label("New Trigger", systemImage: "bolt")
                        }
                    }

                    if createSchedule != nil || createTrigger != nil {
                        Divider()
                    }
                }

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

            // Import menu
            Menu {
                Button(
                    action: { importFiles(.link) },
                    label: {
                        Label(IngestMode.link.displayName, systemImage: IngestMode.link.icon)
                    }
                )

                Button(
                    action: { importFiles(.copy) },
                    label: {
                        Label(IngestMode.copy.displayName, systemImage: IngestMode.copy.icon)
                    }
                )

                Button(
                    action: { importFiles(.move) },
                    label: {
                        Label(IngestMode.move.displayName, systemImage: IngestMode.move.icon)
                    }
                )
            } label: {
                Image(systemName: "square.and.arrow.down")
                    .font(.system(size: 11))
                    .frame(width: 20, height: 20)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Import Files (⌘I)")
        }
        .padding(.horizontal, 8)
        .frame(height: 28)
        .frame(maxWidth: .infinity)  // Ensure full width
        .background(.bar)  // Match mode bar background style
    }
}

// MARK: - View Extensions (Apple's recommended pattern over ViewModifiers)

extension View {
    /// Applies standard sidebar styling (minimum width only).
    /// Note: Individual content views apply their own .listStyle(.sidebar) to their List.
    func sidebarStyle() -> some View {
        self
            .frame(minWidth: SidebarConstants.minimumWidth)
    }
}

/// Configuration for sidebar focused values
struct SidebarFocusedValuesConfig {
    let selectedItem: SidebarItem?
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createSearch: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void          // No longer optional
    let createComparison: () -> Void     // No longer optional
    let createSchedule: () -> Void       // No longer optional
    let createTrigger: () -> Void        // No longer optional
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
                createWorkflow: config.createWorkflow,
                createChain: config.createChain,
                createComparison: config.createComparison,
                createSchedule: config.createSchedule,
                createTrigger: config.createTrigger
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
        performDelete: @escaping @MainActor (SidebarItem) async -> Void
    ) -> some View {
        self.modifier(SidebarDeleteAlertsModifier(
            deleteState: deleteState,
            performDelete: performDelete
        ))
    }
}

private struct SidebarDeleteAlertsModifier: ViewModifier {
    @ObservedObject var deleteState: DeleteStateManager
    let performDelete: @MainActor (SidebarItem) async -> Void

    // `confirmationDialog` is more reliable than `.alert(presenting:)`
    // on macOS inside List(selection:) — the `presenting:`/`isPresented:`
    // pair can race and skip presentation when both @Published fields
    // update in the same tick (#613). The dialog reads itemToDelete at
    // action-fire time, so we only need a single isPresented binding.
    func body(content: Content) -> some View {
        content
            .confirmationDialog(
                deleteState.itemToDelete.map { "Delete \"\($0.name)\"?" } ?? "Delete?",
                isPresented: $deleteState.showingDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    guard let item = deleteState.itemToDelete else { return }
                    Task { @MainActor in
                        await performDelete(item)
                    }
                }
                .keyboardShortcut(.defaultAction)
                Button("Cancel", role: .cancel) {
                    deleteState.cancelDelete()
                }
            } message: {
                Text("This action cannot be undone.")
            }
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
    ///
    /// Accepts `[.item]` (public.item, the root of all file/folder UTTypes) so
    /// case variants like `photo.JPG`, `paper.PDF`, or custom extensions are
    /// not silently filtered by the picker UI. The backend's `detect_file_type`
    /// normalises extensions to lower case (see `ingest.py:154`), so anything
    /// admitted here is classified correctly downstream.
    func sidebarFileImporter(
        isPresented: Binding<Bool>,
        importFiles: @escaping ([URL]) async -> Void
    ) -> some View {
        self.fileImporter(
            isPresented: isPresented,
            allowedContentTypes: [.item],
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
