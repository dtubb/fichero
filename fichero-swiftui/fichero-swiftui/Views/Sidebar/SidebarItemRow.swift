import OSLog
import SwiftUI
import UniformTypeIdentifiers

let sidebarRowLogger = Logger(subsystem: "com.tubb.Fichero", category: "SidebarRow")

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
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager
    @ObservedObject var libraryManager: LibraryManager

    @Environment(WorkflowExecutionObserver.self) var executionObserver

    var library: LibraryManager.LibraryReference? {
        guard let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var documentStore: DocumentStore? { library?.documentStore }
    var savedSearchService: SavedSearchServiceGenerated? { library?.savedSearchServiceGenerated }
    var conversationService: ConversationServiceGenerated? { library?.conversationServiceGenerated }
    var workflowStore: WorkflowStore? { library?.workflowStore }
    var chainService: ChainService? { library?.chainService }
    var automationService: AutomationServiceGenerated? { library?.automationService }
    var importService: ImportServiceGenerated? { library?.importService }

    @State var isDropTargeted = false
    @FocusState var isRenameFocused: Bool
    @State var isCommittingRename = false
    @State var isPulsing = false

    var onItemTapped: ((SidebarItem) -> Void)?
    var onAutomationPause: (() -> Void)?
    var onAutomationResume: (() -> Void)?
    var onAutomationTrigger: (() -> Void)?
    var onAutomationCancel: (() -> Void)?

    var isFolder: Bool {
        guard case .document(let doc) = item.itemType else { return false }
        return doc.docType == .folder
    }

    var workflowIsRunning: Bool {
        guard case .workflow(let workflow) = item.itemType else { return false }
        return executionObserver.isRunning(workflowId: workflow.id)
    }

    var workflowProgress: Double? {
        guard case .workflow(let workflow) = item.itemType else { return nil }
        return executionObserver.getProgress(for: workflow.id)
    }

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    /// Widens `itemLabel`'s hit region to the full available width so the
    /// dropDestination fires when the cursor is anywhere over the row, not
    /// just the icon+text. Tight vertical padding to match Xcode's dense
    /// sidebar rhythm (~18pt row height).
    private var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
    }

    /// Update the drop-target state and log the transition. The log lets Daniel
    /// (or anyone) verify the SwiftUI dropDestination callback is actually
    /// firing via `log stream --subsystem com.tubb.Fichero --predicate
    /// 'category == "SidebarRow"'` — if this line never appears during a drag,
    /// the drop destination isn't registering the hover.
    private func setDropTargeted(_ targeted: Bool) {
        if isDropTargeted != targeted {
            sidebarRowLogger.debug("🎯 \(item.name): dropTargeted=\(targeted)")
            isDropTargeted = targeted
        }
    }

    private var rowContextMenu: some View {
        SidebarItemContextMenu(
            item: item,
            renameState: renameState,
            deleteState: deleteState,
            onPause: onAutomationPause,
            onResume: onAutomationResume,
            onTrigger: onAutomationTrigger,
            onCancel: onAutomationCancel
        )
    }

    var body: some View {
        bodyContent
            .accessibilityLabel(accessibilityLabel)
            .accessibilityHint(accessibilityHint)
            .accessibilityValue(accessibilityValue)
    }

    /// VoiceOver label — the row's displayed name plus its kind so users
    /// who navigate the sidebar non-visually can tell sections apart.
    /// Sidebar plan Step 10 (#584).
    private var accessibilityLabel: String {
        switch item.itemType {
        case .document(let doc):
            return doc.docType == .folder
                ? "\(item.name), folder"
                : "\(item.name), \(doc.fileType?.rawValue ?? "file")"
        case .savedSearch: return "\(item.name), saved search"
        case .conversation: return "\(item.name), conversation"
        case .workflow: return "\(item.name), workflow"
        case .chain: return "\(item.name), workflow chain"
        case .schedule: return "\(item.name), schedule"
        case .trigger: return "\(item.name), trigger"
        case .folder: return "\(item.name), \(item.category.rawValue) folder"
        case .libraryHeader: return "\(item.name), library"
        case .batch, .comparison, .activityRun:
            return item.name
        }
    }

    /// Available actions callable via the context menu. Kept terse so
    /// VoiceOver users don't hear a long recitation each time they land
    /// on a row; power actions like export/duplicate stay discoverable
    /// via `.accessibilityAction` on the context menu itself.
    private var accessibilityHint: String {
        if item.itemType.canBeRenamed {
            return "Double-click to rename. Drag to reorder or move to a folder. Right-click for more actions."
        }
        return "Right-click for actions."
    }

    /// Expansion state for folder rows — read as "expanded"/"collapsed"
    /// so arrow-key navigation via VoiceOver correctly reflects the
    /// DisclosureGroup state.
    private var accessibilityValue: String {
        guard isExpandable else { return "" }
        return expandedItems.contains(item.id) ? "expanded" : "collapsed"
    }

    private var isExpandable: Bool {
        guard let children = item.children else { return false }
        return !children.isEmpty
    }

    // Drop modifiers attach to `fullWidthLabel` — the PARENT row's label —
    // not to the whole DisclosureGroup. Attaching to the DisclosureGroup
    // made its hit region encompass expanded children, so hovering any
    // descendant lit the parent's `isDropTargeted` too and the whole
    // subtree highlighted in blue (reported 2026-04-17). The drop hit-
    // region is still full-row-wide because `fullWidthLabel` stretches
    // `maxWidth: .infinity`; the remaining dead zone is the chevron
    // itself, which SwiftUI renders as a sibling of the label inside
    // the DisclosureGroup's chrome. Accepted trade-off — most drops
    // target the icon or text, not the chevron.
    //
    // `.onInsert(of:)` between-row drops remain disabled because of the
    // SwiftUICore `HomogeneousCollection` crash on macOS 14+; sidebar
    // plan Step 7 (#580) restores them via a custom DropDelegate.
    @ViewBuilder
    private var bodyContent: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
            } label: {
                labelWithDropTarget
            }
        } else {
            labelWithDropTarget
        }
    }

    /// `fullWidthLabel` wrapped with drag-source, drop-destination, and
    /// context-menu modifiers. Using a single `.onDrop(of:isTargeted:
    /// perform:)` that accepts BOTH UTIs (utf8PlainText for internal
    /// sidebar item IDs and fileURL for Finder drags) because attaching
    /// both `.dropDestination(for: String.self)` and `.onDrop(of:
    /// [.fileURL])` to the same view caused SwiftUI to route Finder
    /// drags through the String handler first (where they'd silently
    /// reject) before ever reaching `.onDrop`. Unifying on the older
    /// NSItemProvider API uses one modifier end-to-end.
    ///
    /// `sidebarDropHighlight` goes HERE (on the label), not on the outer
    /// `bodyContent`, so the blue fill only covers the current row —
    /// not any expanded children below.
    private var labelWithDropTarget: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: isFolder)
            .draggable(item.id)
            .onDrop(
                of: [
                    UTType.utf8PlainText,  // internal sidebar drags (item.id)
                    UTType.fileURL,        // Finder file-URL drags
                    UTType.item,           // broadly-typed drags (images, movies, etc.)
                    UTType.movie,
                    UTType.audio,
                    UTType.image
                ],
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }

    /// Routes a drop on this row to the right handler based on provider
    /// contents: sidebar-internal String drags → documentStore move /
    /// service folder-path update; Finder URL drags → ingestion import
    /// into the correct target folder.
    private func handleRowDrop(_ providers: [NSItemProvider]) -> Bool {
        let textProviders = providers.filter {
            $0.canLoadObject(ofClass: NSString.self)
        }
        let urlProviders = providers.filter {
            $0.canLoadObject(ofClass: URL.self)
                && !$0.canLoadObject(ofClass: NSString.self)  // prefer text when both advertise
        }

        // Internal sidebar drag — our `.draggable(item.id)` emits the
        // ID as a String (utf8PlainText UTI).
        if !textProviders.isEmpty {
            Task {
                var ids: [String] = []
                for provider in textProviders {
                    if let str = try? await Self.loadString(from: provider) {
                        ids.append(str)
                    }
                }
                guard !ids.isEmpty else { return }
                if isFolder {
                    _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)
                } else {
                    _ = handleDropBesideItem(itemIDs: ids, targetItem: item)
                }
            }
            return true
        }

        // Finder file drop — use the existing handler, which already
        // loads URLs via NSItemProvider and routes to the correct
        // target folder based on folder-vs-leaf.
        if !urlProviders.isEmpty {
            let target = isFolder ? item : parentFolderItem(of: item)
            return handleProvidersDrop(urlProviders, targetFolder: target)
        }

        return false
    }

    /// Async helper to unwrap a plain-text NSItemProvider into a String.
    /// Matches the `loadURL` helper's pattern on `SidebarItemRow+DropHandlers`.
    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarRowDrop", code: -1))
                }
            }
        }
    }

    @ViewBuilder
    private func childrenList(_ children: [SidebarItem]) -> some View {
        ForEach(children) { child in
            SidebarItemRow(
                item: child,
                allCachedItems: allCachedItems,
                expandedItems: $expandedItems,
                selectedItemId: $selectedItemId,
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager,
                onItemTapped: onItemTapped
            )
            .contentShape(Rectangle())
            .onTapGesture { onItemTapped?(child) }
            .listRowBackground(
                child.id == selectedItemId
                    ? Color.accentColor.opacity(0.18)
                    : Color.clear
            )
            .tag(child.id)
        }
        // Native Apple-provided blue insertion line for sibling reorder
        // (#580 / sidebar plan Step 7 delivered via SwiftUI's .onMove —
        // the right primitive, despite earlier confusion with the
        // .onInsert(of:) crash). Computes the new ID ordering and
        // persists it via `documentStore.reorderDocuments`, which writes
        // back `sort_order` on each document (#572). The sidebar's
        // `SidebarItemBuilder.childOrder` already sorts by sortOrder
        // first, so the next cache rebuild reflects the new order.
        .onMove { source, destination in
            Task { await reorderChildren(children, source: source, destination: destination) }
        }
    }

    /// Compute the reordered sibling list and persist via the backend
    /// reorder endpoint. Only moves documents — non-document children
    /// (saved searches, workflows, chats) don't go through the
    /// documents reorder API and silently return.
    private func reorderChildren(
        _ children: [SidebarItem],
        source: IndexSet,
        destination: Int
    ) async {
        guard let documentStore else { return }
        var reordered = children
        reordered.move(fromOffsets: source, toOffset: destination)
        let docIds = reordered.compactMap { sibling -> String? in
            if case .document(let doc) = sibling.itemType { return doc.id }
            return nil
        }
        guard !docIds.isEmpty else { return }
        do {
            try await documentStore.reorderDocuments(docIds)
            sidebarRowLogger.debug("✅ Reordered \(docIds.count) siblings under \(item.name)")
        } catch {
            sidebarRowLogger.error("❌ Reorder failed: \(error.localizedDescription)")
        }
    }
}
