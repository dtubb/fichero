import OSLog
import SwiftUI

private let sidebarExtLogger = Logger(subsystem: "app.fichero.fichero", category: "SidebarExtensions")

func sidebarDeleteConfirmationMessage(for item: SidebarItem?) -> String {
    guard let item else {
        return "Move this item to Trash? You can put it back later."
    }
    if case .document(let doc) = item.itemType,
       doc.isLinked,
       let path = doc.path {
        return
            "Move the Fichero reference to \"\(item.name)\" to Trash? "
            + "The original file at \(path) stays on disk, and you can put this back later."
    }
    return "Move \"\(item.name)\" to Trash? You can put it back later."
}

/// Delete-confirmation title: names the single item, or the count for a batch.
func sidebarDeleteConfirmationTitle(for items: [SidebarItem]) -> String {
    if items.count > 1 { return "Delete \(items.count) items?" }
    return items.first.map { "Delete \"\($0.name)\"?" } ?? "Delete?"
}

/// Delete-confirmation body: the per-item message for one, a batch line for many.
func sidebarDeleteConfirmationMessage(for items: [SidebarItem]) -> String {
    if items.count > 1 {
        return "Move \(items.count) items to Trash? You can put them back later."
    }
    return sidebarDeleteConfirmationMessage(for: items.first)
}

/// The rows in a selection that can actually be deleted (drops library headers,
/// comparisons, activity runs — anything `canBeDeleted` rejects).
func sidebarDeletableItems(_ items: [SidebarItem]) -> [SidebarItem] {
    items.filter { $0.itemType.canBeDeleted }
}

/// Items the context-menu Delete acts on. Right-clicking a row inside the
/// current multi-selection targets the whole deletable selection (Finder
/// semantics); a row outside the selection targets itself alone. Falls back
/// to the clicked row when nothing in the selection is deletable so the
/// menu item's enabled state still reflects the row under the pointer.
func sidebarContextDeleteTargets(clicked: SidebarItem, selection: [SidebarItem]) -> [SidebarItem] {
    guard selection.count > 1, selection.contains(where: { $0.id == clicked.id }) else {
        return [clicked]
    }
    let deletable = sidebarDeletableItems(selection)
    return deletable.isEmpty ? [clicked] : deletable
}

/// #4292 — the workflow-editor destination for a workflow MIRROR doc row.
///
/// The engine mirrors every workflow into the document tree as a `.file` doc
/// with `prototype_key == "workflow"` sharing the workflow's id. Selecting
/// that row must open the workflow EDITOR, never the document preview (whose
/// container fallback is "No Preview available"). Resolve the live store item
/// by id; when the store hasn't loaded yet (fresh install, first click before
/// `loadWorkflows()` lands) fall back to an id/name placeholder — the editor
/// loads the full definition by id, so routing must not wait on the store.
func sidebarWorkflowDestination(
    for doc: Document,
    workflows: [WorkflowSidebarItem]
) -> WorkflowSidebarItem {
    workflows.first { $0.id == doc.id } ?? WorkflowSidebarItem(id: doc.id, name: doc.name)
}

/// Whether a right-arrow keypress should hand keyboard focus to the content
/// pane instead of being left to the List: only when a NON-expandable leaf is
/// selected. Folder rows keep right-arrow = native expand; no selection keeps
/// native behavior too. Uses `.onKeyPress` pass-through (`.ignored`), never
/// `.onMoveCommand` — that would swallow ALL arrow keys (#560 regression class).
func sidebarShouldExitFocusRight(selectedItem: SidebarItem?) -> Bool {
    guard let selectedItem else { return false }
    return !selectedItem.isExpandable
}

/// Where a sidebar double-click (or trailing open affordance) routes: the
/// row's own library, focusing the row when it is a document/folder; other
/// row kinds open their library without a focused document (matching the
/// row context menu's Open in New Tab/Window, #1685). Returns nil when
/// there is nothing to open — no row, and no library to fall back to.
func sidebarAuxiliaryOpenTarget(
    item: SidebarItem?,
    fallbackLibraryId: UUID?
) -> (libraryId: UUID, documentId: String?)? {
    guard let item else { return nil }
    guard let libraryId = item.libraryId ?? fallbackLibraryId else { return nil }
    if case .document(let doc) = item.itemType {
        return (libraryId, doc.id)
    }
    return (libraryId, nil)
}

#if os(macOS)
/// Whether an app-initiated open should join the key window's tab group,
/// honoring the user's system-wide "Prefer tabs" setting (Finder parity).
/// `.inFullScreen` stays a window here: the sidebar can't cheaply know the
/// key window's full-screen state, and a separate window is the safe default.
func sidebarOpenPrefersTab(_ preference: NSWindow.UserTabbingPreference) -> Bool {
    preference == .always
}
#endif

// MARK: - View Extensions (Apple's recommended pattern over ViewModifiers)

extension View {
    /// Applies standard sidebar styling.
    /// Note: Individual content views apply their own .listStyle(.sidebar) to their List.
    ///
    /// #4301: this used to force an inner minimum-width frame
    /// (200pt) INSIDE the sidebar column. The column's real minimum is owned by
    /// `.navigationSplitViewColumnWidth(min:)` in `ContentView+SidebarLayout`
    /// (160pt); when the split view collapsed the column toward 0pt, the inner
    /// frame kept laying the content out 200pt wide. The List clips itself, but
    /// the bottom toolbar strip does not — so the bottom row stayed painted over
    /// the content column after collapse. The column min lives in ONE place now;
    /// `.clipped()` on the column content is the belt-and-braces guard.
    /// Returns `AnyView` DELIBERATELY (2026-08-08 live crash: the sidebar's
    /// fully-composed concrete type overflowed the stack during SwiftUI's
    /// value-witness copy — the #4331 class, where the erasures are
    /// load-bearing, now on macOS). Do not "simplify" back to `some View`.
    func sidebarStyle() -> AnyView {
        AnyView(self)
    }
}

/// Configuration for sidebar focused values
struct SidebarFocusedValuesConfig {
    let selectedItem: SidebarItem?
    let createFolder: () -> Void
    let importFiles: (IngestMode) -> Void
    let renameItem: () -> Void
    let deleteItem: () -> Void
    let createChat: () -> Void
    let createWorkflow: () -> Void
    let createChain: () -> Void          // No longer optional
    let createComparison: () -> Void     // No longer optional
    let createSchedule: () -> Void       // No longer optional
    let createTrigger: () -> Void        // No longer optional
    let openSelectionInNewTab: () -> Void
    let openSelectionInNewWindow: () -> Void
    /// Deletable rows in the current multi-selection (drives Edit ▸ Delete).
    var deletableSelectionCount: Int = 0
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
                createChat: config.createChat,
                createWorkflow: config.createWorkflow,
                createChain: config.createChain,
                createComparison: config.createComparison,
                createSchedule: config.createSchedule,
                createTrigger: config.createTrigger,
                openSelectionInNewTab: config.openSelectionInNewTab,
                openSelectionInNewWindow: config.openSelectionInNewWindow
            ))
            .focusedValue(\.sidebarSelectionInfo, SidebarSelectionInfo(
                selectedItem: config.selectedItem,
                canRename: config.selectedItem?.itemType.canBeRenamed ?? false,
                canDelete: config.deletableSelectionCount > 0,
                deletableCount: config.deletableSelectionCount
            ))
    }
}

// Note: This extension uses a ViewModifier wrapper because it needs @State bindings
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

    /// Adds an alert for failed sidebar drag moves.
    func sidebarDropAlerts(sidebarState: SidebarState) -> some View {
        self.modifier(SidebarDropAlertsModifier(sidebarState: sidebarState))
    }
}

private struct SidebarDeleteAlertsModifier: ViewModifier {
    @Bindable var deleteState: DeleteStateManager
    let performDelete: @MainActor (SidebarItem) async -> Void

    // `confirmationDialog` is more reliable than `.alert(presenting:)`
    // on macOS inside List(selection:) — the `presenting:`/`isPresented:`
    // pair can race and skip presentation when both fields
    // update in the same tick (#613). The dialog reads itemToDelete at
    // action-fire time, so we only need a single isPresented binding.
    func body(content: Content) -> some View {
        content
            .confirmationDialog(
                sidebarDeleteConfirmationTitle(for: deleteState.itemsToDelete),
                isPresented: $deleteState.showingDeleteConfirmation,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    let items = deleteState.itemsToDelete
                    Task { @MainActor in
                        for item in items {
                            await performDelete(item)
                        }
                    }
                }
                .keyboardShortcut(.defaultAction)
                Button("Cancel", role: .cancel) {
                    deleteState.cancelDelete()
                }
            } message: {
                Text(sidebarDeleteConfirmationMessage(for: deleteState.itemsToDelete))
            }
            .alert("Delete Failed", isPresented: $deleteState.showingDeleteError) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(deleteState.deleteErrorMessage)
            }
    }
}

private struct SidebarDropAlertsModifier: ViewModifier {
    @Bindable var sidebarState: SidebarState

    func body(content: Content) -> some View {
        content
            // "Drop Failed", not "Move Failed": `dropErrorMessage` carries
            // import/read failures too ("Couldn't read the dropped item(s)",
            // "Import failed: …"), and a Finder-drop failure titled "Move
            // Failed" misstates which operation failed (live report
            // 2026-08-04). The MESSAGE names the specific failure — reading
            // vs importing vs moving; the title stays operation-neutral.
            .alert(
                "Drop Failed",
                isPresented: Binding(
                    get: { sidebarState.dropErrorMessage != nil },
                    set: { isPresented in
                        if !isPresented {
                            sidebarState.dropErrorMessage = nil
                        }
                    }
                )
            ) {
                Button("OK", role: .cancel) {
                    sidebarState.dropErrorMessage = nil
                }
            } message: {
                Text(sidebarState.dropErrorMessage ?? "The drop could not be completed.")
            }
            .modifier(sidebarMessageAlert(
                title: "Rename Failed",
                fallback: "The rename could not be completed.",
                message: Binding(
                    get: { sidebarState.renameErrorMessage },
                    set: { sidebarState.renameErrorMessage = $0 }
                )
            ))
            .modifier(sidebarMessageAlert(
                title: "Alias Can’t Be Opened",
                fallback: "The original item can’t be found.",
                message: Binding(
                    get: { sidebarState.aliasErrorMessage },
                    set: { sidebarState.aliasErrorMessage = $0 }
                )
            ))
    }
}

/// One-line dismissable error alert bound to an optional message — shared by
/// the rename and alias failure surfaces (and any future one-message alert).
private func sidebarMessageAlert(
    title: String,
    fallback: String,
    message: Binding<String?>
) -> SidebarMessageAlertModifier {
    SidebarMessageAlertModifier(title: title, fallback: fallback, message: message)
}

private struct SidebarMessageAlertModifier: ViewModifier {
    let title: String
    let fallback: String
    @Binding var message: String?

    func body(content: Content) -> some View {
        content.alert(
            title,
            isPresented: Binding(
                get: { message != nil },
                set: { isPresented in
                    if !isPresented {
                        message = nil
                    }
                }
            )
        ) {
            Button("OK", role: .cancel) {
                message = nil
            }
        } message: {
            Text(message ?? fallback)
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
    @Bindable var sidebarState: SidebarState
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
                sidebarExtLogger.debug("File import cancelled or failed: \(error.localizedDescription)")
            }
        }
    }
}
