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

/// Visibility rule for the trailing hover open-affordance (#2496): only while
/// the pointer is over the row, never during an inline rename (the field owns
/// the trailing space), and only for rows that can actually be opened
/// (rows without a library have nowhere to route).
func sidebarRowShowsOpenAffordance(isHovered: Bool, isRenaming: Bool, hasLibrary: Bool) -> Bool {
    isHovered && !isRenaming && hasLibrary
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
    func sidebarDropHighlight(
        _ active: Bool, stronger: Bool, operation: SidebarDropOperation = .move
    ) -> some View {
        // Modifier-drag tint — the closest native stand-in for AppKit's
        // drag-cursor badges, which SwiftUI's row drag doesn't expose (no
        // sourceOperationMask hook): ⌥ copy = green, ⌘⌥ alias = purple.
        let tint: Color = switch operation {
        case .move: Color.accentColor
        case .copy: Color.green
        case .alias: Color.purple
        }
        self.overlay(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(
                    active
                        ? tint.opacity(stronger ? 0.45 : 0.25)
                        : Color.clear
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                        .stroke(
                            active ? tint : Color.clear,
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
    let selectedDestinations: Set<SidebarDestination>
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
    /// Pointer-over state driving the trailing open affordance (#2496).
    @State var isRowHovered = false
    /// ⌥/⌘ held while this row is a drop target → copy/alias highlight tint.
    /// Tracked by a flagsChanged monitor installed ONLY while targeted
    /// (macOS; one row is targeted at a time so at most one monitor lives).
    @State var isOptionHeldOverTarget = false
    @State var isCommandHeldOverTarget = false
    #if os(macOS)
    @State private var optionMonitor: Any?
    #endif
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
                    // NOTE: the old guard required a positive child count, but
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
            // Full name on hover — row names truncate (`lineLimit(1)`) with no
            // other way to reveal themselves. Empty string disables the tooltip
            // during inline rename (same idiom as the read-only library help).
            // The trailing affordance's own `.help` wins over its frame.
            .help(renameState.renamingItemId == item.id ? "" : item.name)
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

    #if os(macOS)
    /// Track ⌥ while this row is targeted so the highlight can tint to copy
    /// mode live. Note: whether flagsChanged reaches a local monitor during
    /// an active drag session needs a gate eyeball; the drop BEHAVIOR reads
    /// the key again at drop time regardless (`sidebarOptionKeyIsHeld`).
    func updateOptionMonitor(targeted: Bool) {
        if targeted {
            isOptionHeldOverTarget = NSEvent.modifierFlags.contains(.option)
            isCommandHeldOverTarget = NSEvent.modifierFlags.contains(.command)
            guard optionMonitor == nil else { return }
            optionMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
                isOptionHeldOverTarget = event.modifierFlags.contains(.option)
                isCommandHeldOverTarget = event.modifierFlags.contains(.command)
                return event
            }
        } else {
            if let optionMonitor {
                NSEvent.removeMonitor(optionMonitor)
            }
            optionMonitor = nil
            isOptionHeldOverTarget = false
            isCommandHeldOverTarget = false
        }
    }
    #endif

    /// The operation the CURRENT modifiers would perform on this drop target —
    /// drives the highlight tint only; the drop re-reads the keys itself.
    var targetedDropOperation: SidebarDropOperation {
        sidebarDropOperation(
            optionHeld: isOptionHeldOverTarget,
            commandHeld: isCommandHeldOverTarget,
            kind: .document
        )
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
