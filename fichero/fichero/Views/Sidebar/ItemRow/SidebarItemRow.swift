import OSLog
import SwiftUI
import UniformTypeIdentifiers
#if canImport(AppKit)
import AppKit
#endif

let sidebarRowLogger = Logger(subsystem: "app.fichero.fichero", category: "SidebarRow")

func sidebarSelectionFallback(current: String?, tapped: String) -> String? {
    current == tapped ? nil : tapped
}

/// Whether a restored/persisted sidebar selection still needs to be driven into
/// the view mode (#2548). `selectedItemId` is restored from `@SceneStorage` at
/// launch, but `SidebarView.onChange(of: selectedItemId)` only fires on a
/// *change* — so a restored selection that equals the persisted value never
/// reaches `handleSelection`, leaving `viewMode` at its default. The visibly
/// highlighted row then doesn't match the detail, and clicking that
/// already-selected row is a no-op (native `List(selection:)` sees no change and
/// the tap fallback guards `current == tapped`). Reconcile when a selection
/// exists but hasn't been handled yet.
func sidebarShouldReconcileSelection(selectedId: String?, lastHandled: String?) -> Bool {
    guard let selectedId else { return false }
    return selectedId != lastHandled
}

/// Transferable wrapper for sidebar row drags (#711).
///
/// Two reasons this exists rather than `.draggable(item.id)` directly:
///   1. `visibility(.ownProcess)` keeps the drag invisible to external
///      apps, preserving the #623 fix that prevented Finder from
///      depositing an HTML link artifact when dragging out of the sidebar.
///   2. Advertising a Transferable on the row makes AppKit's NSTableView
///      row-drag (which List uses under the hood) pull THIS payload
///      instead of synthesizing an empty `public.file-url` when it wins
///      the gesture arena over `.onDrag` — the root cause of #711's
///      "Files dropped: [\"\"]" leak when grabbing from icon/text.
///
/// The bridged NSItemProvider responds to `loadObject(ofClass: NSString.self)`
/// in-process, which is what `SidebarItemRow.handleRowDrop` already filters
/// for — so the drop pipeline didn't need migrating.
struct SidebarDragID: Transferable {
    let id: String
    static var transferRepresentation: some TransferRepresentation {
        ProxyRepresentation(exporting: \.id)
            .visibility(.ownProcess)
    }
}

extension View {
    /// Applies the sidebar drop-target highlight (accent fill + stroke) to
    /// any view. Placed on the OUTER expression of a SidebarItemRow body
    /// branch so it covers the full List row — including the DisclosureGroup
    /// chevron/indent area that `fullWidthLabel` alone can't reach.
    ///
    /// `.overlay` + `.allowsHitTesting(false)` so the wash renders on top of
    /// whatever chrome the sidebar-style List draws, without blocking drops.
    @ViewBuilder
    func sidebarDropHighlight(_ active: Bool, stronger: Bool) -> some View {
        self.overlay(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(
                    active
                        ? Color.accentColor.opacity(stronger ? 0.45 : 0.25)
                        : Color.clear
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                        .stroke(
                            active ? Color.accentColor : Color.clear,
                            lineWidth: active ? 2 : 0
                        )
                )
                .allowsHitTesting(false)
        )
    }
}

struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @Binding var selectedItemId: String?
    @Bindable var renameState: RenameStateManager
    @Bindable var deleteState: DeleteStateManager
    @Bindable var sidebarState: SidebarState
    @Bindable var libraryManager: LibraryManager
    var onOpenChatWithCurrentScope: (() -> Void)?

    @Environment(WorkflowExecutionObserver.self) var executionObserver
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

    @State var isDropTargeted = false
    @State var workflowRunProviderCache = WorkflowRunProviderCache.shared
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

    var workflowIsRunning: Bool {
        guard case .workflow(let workflow) = item.itemType else { return false }
        return executionObserver.isRunning(workflowId: workflow.id)
    }

    /// True when this sidebar row's document is currently being processed
    /// by a workflow, OR (for folders) any of its direct children is. Drives
    /// a sidebar spinner so users can see processing activity even when the
    /// item isn't visible in the grid. (#785)
    ///
    /// Reads `Document.status` from the live `DocumentStore` rather than the
    /// captured `SidebarItem.itemType` snapshot — the store is what the
    /// workflow stream mutates via `updateProcessingStatus(forPath:status:)`.
    var documentIsProcessing: Bool {
        guard case .document(let doc) = item.itemType, let store = documentStore else {
            return false
        }
        let live = store.currentDocuments.first(where: { $0.id == doc.id })
            ?? store.collections.first(where: { $0.id == doc.id })
            ?? doc
        if live.status == .processing { return true }
        // Folder: report processing if ANY descendant is currently processing.
        // Look in BOTH currentDocuments (the set actively shown in the grid;
        // covers the very common "user is browsing the folder being processed"
        // case the user hit) and childrenCache (other folders' kids cached for
        // sidebar tree expansion). Without the currentDocuments check the
        // folder spinner only appeared if the user had expanded the folder
        // separately — silently broken in the most common workflow.
        if doc.docType == .folder {
            if store.currentDocuments.contains(where: {
                $0.parentId == doc.id && $0.status == .processing
            }) {
                return true
            }
            if let kids = store.childrenCache[doc.id],
               kids.contains(where: { $0.status == .processing }) {
                return true
            }
        }
        return false
    }

    var workflowProgress: Double? {
        guard case .workflow(let workflow) = item.itemType else { return nil }
        return executionObserver.getProgress(for: workflow.id)
    }

    var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                    guard case .document(let document) = item.itemType,
                          let store = documentStore else { return }
                    // NOTE: the old guard required `document.childCount > 0`, but
                    // the backend never sends child_count on getRoots/getChildren
                    // (it decodes to 0), so that guard was dead and children only
                    // ever loaded as a side-effect of SELECTING the folder — the
                    // #3355 root cause. Load whenever they aren't cached yet.
                    #if canImport(AppKit)
                    let optionHeld = NSApp.currentEvent?.modifierFlags.contains(.option) ?? false
                    #else
                    let optionHeld = false
                    #endif
                    if optionHeld {
                        // Option-click: expand the WHOLE subtree, Finder-style.
                        Task { await expandSubtree(document, store: store) }
                    } else if item.children == nil, store.childrenCache[document.id] == nil {
                        Task { await store.loadSidebarChildren(of: document) }
                    }
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    /// Option-click expands the ENTIRE subtree (Finder), lazily loading each
    /// level. An explicit user gesture, so the deep fan-out fetch is acceptable
    /// — unlike the bounded one-level prefetch in `loadSidebarChildren`.
    @MainActor
    func expandSubtree(_ document: Document, store: DocumentStore) async {
        expandedItems.insert("doc:\(document.id)")
        let children = await store.cacheSidebarChildren(of: document)
        for child in children where child.docType == .folder {
            await expandSubtree(child, store: store)
        }
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
