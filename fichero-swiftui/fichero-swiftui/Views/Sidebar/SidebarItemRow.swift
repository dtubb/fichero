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

    @ViewBuilder
    private var bodyContent: some View {
        rowShape
            .draggable(item.id)
            .dropDestination(for: String.self) { droppedIDs, _ in
                if isFolder {
                    handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                } else {
                    handleDropBesideItem(itemIDs: droppedIDs, targetItem: item)
                }
            }
            .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
                // Folder drop → import into this folder. Leaf drop → import
                // into the leaf's parent folder ("drop beside" semantics
                // for sibling imports next to a file). Non-document leaves
                // fall through to the library root when parentFolderItem
                // returns nil.
                let target = isFolder ? item : parentFolderItem(of: item)
                return handleProvidersDrop(providers, targetFolder: target)
            }
            .contextMenu { rowContextMenu }
    }

    // Whole-row container. For folders with children, wraps the label
    // in a `DisclosureGroup` so the chevron shows; for empty folders and
    // leaves, renders just the label. Drop/drag modifiers attach to
    // `rowShape` itself (not inside the DisclosureGroup's label closure)
    // so the chevron/indent area is a full-width drop target — fix for
    // the 2026-04-17 review finding that drops missed the chevron
    // because modifiers were bound to the label subview only (#598).
    //
    // `.onInsert(of:)` between-row drops remain disabled because of the
    // SwiftUICore `HomogeneousCollection` crash on macOS 14+. Sidebar
    // plan Step 7 (#580) restores them via a custom DropDelegate.
    @ViewBuilder
    private var rowShape: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
            } label: {
                fullWidthLabel
            }
        } else {
            fullWidthLabel
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
