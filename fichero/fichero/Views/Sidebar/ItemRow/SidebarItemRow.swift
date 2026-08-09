import OSLog
import SwiftUI
import UniformTypeIdentifiers
#if canImport(AppKit)
import AppKit
#endif
#if canImport(PDFKit)
import PDFKit
#endif

let sidebarRowLogger = Logger(subsystem: "app.fichero.fichero", category: "SidebarRow")

/// Visibility rule for the trailing hover open-affordance (#2496): only while
/// the pointer is over the row, never during an inline rename (the field owns
/// the trailing space), and only for rows that can actually be opened
/// (rows without a library have nowhere to route).
func sidebarRowShowsOpenAffordance(isHovered: Bool, isRenaming: Bool, hasLibrary: Bool) -> Bool {
    isHovered && !isRenaming && hasLibrary
}

// The hover WASH (#4097) and the hover name TOOLTIP were removed on Daniel's
// direction (2026-08-08): the name area read as a second interactive target
// on top of the row itself. The only remaining hover behaviour is the
// trailing open affordance (#2496), which `isRowHovered` still drives.
// `SidebarHoverWashTests` pins the absence.

/// Whether a restored/persisted sidebar selection still needs to be driven into
/// the view mode (#2548). `selectedItemId` is restored from `@SceneStorage` at
/// launch, but `SidebarView.onChange(of: selectedItemId)` only fires on a
/// *change* — so a restored selection that equals the persisted value never
/// reaches `handleSelection`, leaving `viewMode` at its default. The visibly
/// highlighted row then doesn't match the detail, and clicking that
/// already-selected row is a no-op (native `List(selection:)` sees no
/// change). Reconcile when a selection exists but hasn't been handled yet.
func sidebarShouldReconcileSelection(selectedId: String?, lastHandled: String?) -> Bool {
    guard let selectedId else { return false }
    return selectedId != lastHandled
}

struct SidebarItemRow: View {
    let item: SidebarItem
    /// O(1) row resolution by id, backed by `SidebarView.cachedItemIndex`.
    ///
    /// #4545: this used to be `allCachedItems: [SidebarItem]` — the WHOLE
    /// cached forest stored in EVERY row, so SwiftUI copied it with each of
    /// the ~740 row copies the aug4 profile measured, and every walk-based
    /// lookup (`findItemById`) re-traversed the tree the index had already
    /// flattened. Every use was an id lookup; a closure is 16 bytes.
    let lookupItem: (String) -> SidebarItem?
    @Binding var expandedItems: Set<String>
    @Binding var selectedItemId: String?
    let selectedDestinations: Set<SidebarDestination>
    @Bindable var renameState: RenameStateManager
    @Bindable var deleteState: DeleteStateManager
    @Bindable var sidebarState: SidebarState
    @Bindable var libraryManager: LibraryManager
    var onOpenChatWithCurrentScope: (() -> Void)?

    @Environment(WorkflowExecutionObserver.self) var executionObserver
    @Environment(WindowState.self) var windowState
    /// Finder-style Open in New Tab / New Window for sidebar rows (#1685).
    @Environment(\.openWindow) private var openWindow
    @Environment(\.horizontalSizeClass) var horizontalSizeClass
    var library: LibraryManager.LibraryReference? {
        guard let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var documentStore: DocumentStore? { library?.documentStore }
    var savedSearchService: SavedSearchService? { library?.savedSearchService }
    var conversationService: ConversationService? { library?.conversationService }
    var workflowStore: WorkflowStore? { library?.workflowStore }
    var chainService: ChainService? { library?.chainService }
    var automationService: AutomationAPIService? { library?.automationService }
    var importService: ImportService? { library?.importService }

    /// Contiguous-selection merging (2026-08-09): true when the row directly
    /// above/below in the SAME list is also selected — the platter squares
    /// that edge so a block selection reads as one squircle.
    var mergeSelectionAbove: Bool = false
    var mergeSelectionBelow: Bool = false

    @State var isDropTargeted = false
    /// Pointer-over state driving the trailing open affordance (#2496).
    @State var isRowHovered = false
    @State var workflowRunProviderCache = WorkflowRunProviderCache.shared
    /// Grid-menu parity (#4121): Bookmark… / Add to Workspace… picker sheets,
    /// presented from this row so each row injects ITS library's services.
    @State var workspacePickerDocument: Document?
    @State var bookmarkPickerDocument: Document?
    @FocusState var isRenameFocused: Bool
    @State var isCommittingRename = false
    @State var isPulsing = false

    var onAutomationPause: (() -> Void)?
    var onAutomationResume: (() -> Void)?
    var onAutomationTrigger: (() -> Void)?
    var onAutomationCancel: (() -> Void)?

    var isFolder: Bool {
        guard case .document(let doc) = item.itemType else { return false }
        return doc.docType == .folder
    }

    /// Inbox is a protected root-level folder (like Finder's "Downloads"
    /// or Mail's "Inbox") — always at the top, never a drag source.
    /// Matches the `buildInboxItem` builder in `SidebarItemBuilder` that
    /// stamps the "tray.fill" icon onto the library's Inbox doc.
    var isInboxFolder: Bool {
        item.icon == "tray.fill"
    }

    /// The workflow id whose run-state this row should display, or nil for
    /// non-workflow rows. Mirror DOC rows share their workflow's id (the
    /// engine mirrors workflows into same-id document nodes), so the sidebar
    /// spinner survives #4186's removal of the virtual workflow rows.
    /// Static + pure for testability (nonisolated: statics on View types
    /// inherit MainActor under the macOS 26 SDK and tests run off-main).
    nonisolated static func runStateWorkflowId(for item: SidebarItem) -> String? {
        switch item.itemType {
        case .workflow(let workflow):
            return workflow.id
        case .document(let doc) where doc.isWorkflowNode:
            return doc.id
        default:
            return nil
        }
    }

    var workflowIsRunning: Bool {
        guard let workflowId = Self.runStateWorkflowId(for: item) else { return false }
        return executionObserver.isRunning(workflowId: workflowId)
    }

    /// True when this sidebar row's document is currently being processed
    /// by a workflow, OR (for folders) any of its direct children is. Drives
    /// a sidebar spinner so users can see processing activity even when the
    /// item isn't visible in the grid. (#785)
    ///
    /// Reads `Document.status` from the live `DocumentStore` rather than the
    /// captured `SidebarItem.itemType` snapshot — the store is what the
    /// workflow stream mutates via `updateProcessingStatus(forPath:status:)`.
    /// What this row should indicate, separating work ON this document from
    /// work on its CONTENTS (#4417).
    ///
    /// The aggregation is unchanged from #4295 — the same sources, the same
    /// tolerance for stale container copies. What changed is that a busy child
    /// no longer collapses into the parent's own spinner.
    var containerActivity: ContainerActivity {
        guard case .document(let doc) = item.itemType, let store = documentStore else {
            return .idle
        }
        // #4295: busy is derived from the RUNNING EXECUTION'S TARGETS
        // (status overrides + every live container, including the sidebar's
        // childrenCache), never from selection-scoped state — the old lookup
        // stopped at currentDocuments/collections, so a page row's spinner
        // only rendered while its parent was the selected collection.
        let isSelfProcessing = store.isDocumentBusy(doc.id) || doc.status == .processing

        // Any container aggregates, not only folders: the reported case was a
        // PDF spinning alongside its four page children.
        let counts = store.childActivityCounts(of: doc.id)

        return ContainerActivity.resolve(
            isSelfProcessing: isSelfProcessing,
            busyChildren: counts.busy,
            totalChildren: counts.total
        )
    }

    /// The per-item spinner, now only for a document that is itself the
    /// subject of work. A container with busy children shows the aggregate.
    var documentIsProcessing: Bool {
        containerActivity.showsLeafSpinner
    }

    var workflowProgress: Double? {
        guard let workflowId = Self.runStateWorkflowId(for: item) else { return nil }
        return executionObserver.getProgress(for: workflowId)
    }

    var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                    guard case .document(let document) = item.itemType,
                          let store = documentStore else { return }
                    // NOTE: the old guard required a positive child count and
                    // was dead — not because the backend omits `child_count`
                    // (it does not; that premise was wrong, #4515) but because
                    // the client's converter dropped the typed field, so every
                    // folder decoded 0. Children then loaded only as a
                    // side-effect of SELECTING the folder — the #3355 root
                    // cause. Load whenever they aren't cached yet: the count
                    // is now honest, and re-adding the guard would still be
                    // wrong for a folder whose count arrived after expansion.
                    #if canImport(AppKit)
                    let optionHeld = NSApp.currentEvent?.modifierFlags.contains(.option) ?? false
                    #else
                    let optionHeld = false
                    #endif
                    if optionHeld {
                        // Option-click: expand the WHOLE subtree, Finder-style.
                        Task {
                            await sidebarExpandSubtree(
                                document, store: store, expandedItems: $expandedItems
                            )
                        }
                    } else {
                        // #4293: ALWAYS run the one-level load+prefetch on
                        // expand. The old guard skipped it when this row's
                        // children were already cached (e.g. by the root-level
                        // prefetch in loadCollections) — but loadSidebarChildren
                        // is ALSO what prefetches the grandchildren, so a
                        // prefetched folder's SUBfolders (workflow folders
                        // under "Default Workflows", a folder of folders two
                        // levels down) never got children cached, rendered
                        // chevron-less, and could not be expanded at all.
                        // Idempotent + cheap when everything is cached:
                        // cacheSidebarChildren returns the cache hit and
                        // containersNeedingChildren comes back empty.
                        Task { await store.loadSidebarChildren(of: document) }
                    }
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    /// Widens `itemLabel`'s hit region to the full available width so
    /// drops fire when the cursor is anywhere over the row, not just on
    /// the icon+text. Tight vertical padding to match Xcode's dense
    /// sidebar rhythm (~18pt row height).
    ///
    /// No `.draggable` here — that lives on the outer row container in
    /// the `ForEach`. A `.draggable` placed inside a `DisclosureGroup`
    /// label's `NSHostingView` creates a side-channel drag session that
    /// bypasses NSTableView's row-drag mechanism, producing a small
    /// label-only preview and silently skipping `.dropDestination` on
    /// the ForEach (#711).
    var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            // No hover wash and no name tooltip here — removed on Daniel's
            // direction (2026-08-08): both made the NAME read as its own
            // interactive target layered on the row. `onHover` stays solely
            // to drive the trailing open affordance (#2496); the row's only
            // highlight is the List's native selection.
            #if os(macOS)
            .onHover { isRowHovered = $0 }
            #endif
    }

    /// Document id when this sidebar row represents a document or folder —
    /// used to focus it after opening in a new tab/window (#1685).
    var openableDocumentId: String? {
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    }

    /// In-window "Open": select this row (drives navigation/preview).
    func openInWindow() {
        selectedItemId = item.id
    }

    /// "Open in New Tab / New Window": open a fresh window on this item's
    /// library via the shared Safari new-window path. For document/folder rows
    /// the document is focused once the new window loads; other item types open
    /// the library and leave deeper focus as a follow-up.
    func openInNewWindow(asTab: Bool) {
        // Follow-up (#1685): focus non-document sidebar items (saved
        // searches, workflows, chats) in the new window — needs a pending
        // sidebar selection consumed by SidebarView, mirroring
        // pendingOpenDocumentId.
        guard let libraryId = item.libraryId ?? libraryManager.currentLibraryId else { return }
        WindowOpener.open(
            libraryId: libraryId,
            documentId: openableDocumentId,
            asTab: asTab,
            using: openWindow
        )
    }

}
