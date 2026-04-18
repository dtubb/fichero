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

    // Folders (with or without children) are drop targets; leaves
    // (PDFs, images, saved searches, etc.) are drag sources only.
    // Matches Finder semantics: you can drag a file out, but you
    // can't drop anything onto a file.
    @ViewBuilder
    private var bodyContent: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
            } label: {
                folderLabel
            }
        } else if isFolder {
            folderLabel
        } else {
            leafLabel
        }
    }

    /// Folder row: drag source + drop target.
    /// `.utf8PlainText` handles internal sidebar drags; `.item` is the
    /// root UTType conforming to every file / folder type so Finder
    /// drops match without enumerating each concrete UTI.
    private var folderLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: true)
            .draggable(item.id)
            .onDrop(
                of: [UTType.utf8PlainText, UTType.item],
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }

    /// Leaf row: drag source only. PDFs, images, saved searches,
    /// conversations, workflows can all be DRAGGED to another
    /// folder, but dropping anything onto a leaf doesn't match
    /// Finder semantics — you can't drop a file onto a file.
    private var leafLabel: some View {
        fullWidthLabel
            .draggable(item.id)
            .contextMenu { rowContextMenu }
    }

    /// Optimistic accept: any provider that can produce a URL or String
    /// returns true immediately; async loading continues in background.
    /// Synchronous `canLoadObject` pre-filtering misses URL-producing
    /// items because macOS advertises some capabilities asynchronously.
    private func handleRowDrop(_ providers: [NSItemProvider]) -> Bool {
        #if DEBUG
        sidebarRowLogger.debug("📥 handleRowDrop fired on \(item.name) with \(providers.count) provider(s)")
        for (idx, provider) in providers.enumerated() {
            let utis = provider.registeredTypeIdentifiers.joined(separator: ", ")
            let canURL = provider.canLoadObject(ofClass: URL.self)
            let canString = provider.canLoadObject(ofClass: NSString.self)
            sidebarRowLogger.debug("  [\(idx)] UTIs: [\(utis)]  URL:\(canURL)  String:\(canString)")
        }
        #endif

        guard !providers.isEmpty else { return false }

        // Providers that can ONLY load String (not URL) are internal
        // sidebar drags — `.draggable(item.id)` advertises the String via
        // utf8PlainText. Route them through the sidebar-internal path.
        let textOnly = providers.filter {
            !$0.canLoadObject(ofClass: URL.self) && $0.canLoadObject(ofClass: NSString.self)
        }

        if !textOnly.isEmpty {
            Task {
                var ids: [String] = []
                for provider in textOnly {
                    if let str = try? await Self.loadString(from: provider) {
                        ids.append(str)
                    }
                }
                guard !ids.isEmpty else { return }
                _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)
            }
            return true
        }

        // Anything else — Finder drags with URL or content UTIs — goes
        // through the optimistic Finder-import path.
        _ = handleProvidersDrop(providers, targetFolder: item)
        return true
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
                libraryManager: libraryManager
            )
            .contentShape(Rectangle())
            .tag(child.id)
        }
        // Same-list reorder within this folder's children. SwiftUI routes
        // drags whose id IS already present in `children` through
        // `.onMove`; cross-hierarchy drops of NEW ids fire
        // `.dropDestination` below — they don't double-fire.
        .onMove { source, destination in
            guard let store = documentStore,
                  let orderedIds = sidebarReorderedDocIds(
                      children: children,
                      moving: source,
                      to: destination
                  ) else { return }
            store.reorderChildrenOptimistically(orderedIds: orderedIds)
        }
        // Cross-hierarchy insertion drop: drag a folder/PDF from ANOTHER
        // part of the tree and drop it at `offset` to become a child of
        // THIS folder at that position. Guards:
        //   - Only "doc:" prefixed ids (documents / folders) are accepted;
        //     saved searches, workflows, etc. have their own reorder paths.
        //   - Cycle rejection via `isDescendant(item.id, of: "doc:<bareId>")`:
        //     this catches both self-drop (A onto A) AND ancestor-as-child
        //     (A onto B where A is B's ancestor), because `containsDescendant`
        //     treats self as descendant.
        //   - Only folder parents accept child drops — PDFs and leaf file
        //     rows don't reach this code path since they render via
        //     `leafLabel` (no DisclosureGroup wrapper, no `childrenList`).
        .dropDestination(for: String.self) { droppedIds, offset in
            handleNestedInsertionDrop(droppedIds: droppedIds, at: offset, into: children)
        }
    }

    private func handleNestedInsertionDrop(
        droppedIds: [String],
        at offset: Int,
        into children: [SidebarItem]
    ) {
        guard case .document(let parentDoc) = item.itemType,
              parentDoc.docType == .folder,
              let store = documentStore else {
            return
        }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
            .filter { bareId in
                // Reject cycle: can't make self a child of self, nor make an
                // ancestor a child of its descendant.
                !isDescendant(item.id, of: "doc:\(bareId)")
            }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: children,
            inserting: bareIds,
            at: offset
        ) else { return }

        Task {
            for bareId in bareIds {
                _ = try? await store.moveDocument(bareId, toParent: parentDoc.id)
            }
            await MainActor.run {
                store.reorderChildrenOptimistically(orderedIds: newOrder)
            }
        }
    }
}

// MARK: - Preview

/// Self-contained visual preview of the sidebar's List + DisclosureGroup
/// + Label stack. No backend, no services, no bindings to real state —
/// just static SwiftUI so we can iterate on fonts, selection highlight,
/// and section-header weight via Xcode Previews (or
/// `mcp__xcode__RenderPreview`).
///
/// Keep this in sync with the styling choices in `LibrarySectionHeader`,
/// `SidebarView+ViewComponents.unifiedDisclosureSection`, and any other
/// rendering-only detail the real sidebar applies.
#Preview("Sidebar look") {
    SidebarVisualPreview()
        .frame(width: 260, height: 500)
}

private struct SidebarVisualPreview: View {
    @State private var selection: String? = "doc-a"
    @State private var librariesExpanded = true
    @State private var searchesExpanded = true

    var body: some View {
        List(selection: $selection) {
            Section {
                DisclosureGroup(isExpanded: $librariesExpanded) {
                    row(id: "doc-a", name: "Inbox", icon: "tray")
                    row(id: "doc-b", name: "Chota Valley", icon: "folder")
                    row(id: "doc-c", name: "Small Text", icon: "folder")
                    row(id: "doc-d", name: "Working", icon: "folder")
                } label: {
                    Text("Library")
                        .font(.caption)
                        .fontWeight(.bold)
                }
                DisclosureGroup(isExpanded: $searchesExpanded) {
                    row(id: "search-a", name: "New Search", icon: "magnifyingglass")
                    row(id: "search-b", name: "Colombia", icon: "magnifyingglass")
                    row(id: "search-c", name: "belcher", icon: "magnifyingglass")
                } label: {
                    Text("Saved Searches")
                        .font(.caption)
                        .fontWeight(.bold)
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
    }

    @ViewBuilder
    private func row(id: String, name: String, icon: String) -> some View {
        Label(name, systemImage: icon)
            .tag(id)
    }
}
