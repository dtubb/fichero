import OSLog
import SwiftUI
import UniformTypeIdentifiers

let sidebarRowLogger = Logger(subsystem: "com.fichero.app", category: "SidebarRow")

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
    /// just the icon+text.
    private var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 2)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
    }

    /// Update the drop-target state and log the transition. The log lets Daniel
    /// (or anyone) verify the SwiftUI dropDestination callback is actually
    /// firing via `log stream --subsystem com.fichero.app --predicate
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
            .sidebarDropHighlight(isDropTargeted, stronger: isFolder)
    }

    @ViewBuilder
    private var bodyContent: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
                // `.onInsert(of:)` on this nested ForEach inside
                // DisclosureGroup inside List triggers a SwiftUICore crash
                // (`HomogeneousCollection index -1 out of bounds`) during
                // external folder drops. Apple's own radar; reproduces
                // reliably on macOS 14+. Between-row drop UX (native blue
                // insertion line) is disabled until we have a safer
                // mechanism — a custom DropDelegate (#580, sidebar plan
                // Step 7) will add back the insertion line with y-threshold
                // regions. Per-row drops (see `folderDropTarget` below)
                // still work — drops land on whatever folder/leaf row
                // the cursor is over.
            } label: {
                fullWidthLabel.folderDropTarget(for: self)
            }
        } else if isFolder {
            fullWidthLabel.folderDropTarget(for: self)
        } else {
            fullWidthLabel.leafDropTarget(for: self)
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
    }
}

// MARK: - Drop Target Modifiers
//
// Extracted so the two folder branches (with/without children) share a
// single drop-target modifier, and the leaf branch has its own with
// "drop beside" semantics. Keeps the three `bodyContent` branches
// small and makes it obvious which shape accepts which drop. Step 7
// (DropDelegate for between-row insertion) only needs to augment the
// `folderDropTarget` — leaf rows never receive between-row drops.

extension View {
    /// Drop modifier for folder rows (both has-children and empty
    /// folders). Accepts:
    /// - Internal sidebar item IDs (`.draggable(item.id)` payload) via
    ///   `dropDestination(for: String.self)` → `handleDropIntoFolder`.
    /// - Finder file URLs via `.onDrop(of: [.fileURL])` → `handleProvidersDrop`.
    ///   Uses NSItemProvider (not Transferable `URL.self`) to preserve
    ///   folder URLs intact (#587, MEMORY.md).
    fileprivate func folderDropTarget(for row: SidebarItemRow) -> some View {
        self.draggable(row.item.id)
            .dropDestination(for: String.self) { droppedIDs, _ in
                row.handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: row.item)
            }
            .onDrop(of: [UTType.fileURL], isTargeted: row.$isDropTargeted) { providers in
                row.handleProvidersDrop(providers, targetFolder: row.item)
            }
            .contextMenu { row.rowContextMenuPublic }
    }

    /// Drop modifier for leaf (non-folder) rows. Accepts:
    /// - Internal sidebar item IDs via `handleDropBesideItem` — sibling
    ///   reparent rather than nesting.
    /// - Finder file URLs that flow to the leaf's parent folder (or the
    ///   library root if the leaf has no parent).
    fileprivate func leafDropTarget(for row: SidebarItemRow) -> some View {
        self.draggable(row.item.id)
            .dropDestination(for: String.self) { droppedIDs, _ in
                row.handleDropBesideItem(itemIDs: droppedIDs, targetItem: row.item)
            }
            .onDrop(of: [UTType.fileURL], isTargeted: row.$isDropTargeted) { providers in
                row.handleProvidersDrop(
                    providers,
                    targetFolder: row.parentFolderItem(of: row.item)
                )
            }
            .contextMenu { row.rowContextMenuPublic }
    }
}

extension SidebarItemRow {
    /// Re-expose the context-menu builder so the drop-modifier extensions
    /// (which can't see `private`) can attach it. Same content, same
    /// identity — just a public alias.
    var rowContextMenuPublic: some View {
        rowContextMenu
    }
}
