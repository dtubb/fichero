import OSLog
import SwiftUI
import UniformTypeIdentifiers

let sidebarRowLogger = Logger(subsystem: "com.fichero.app", category: "SidebarRow")

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

    /// Wraps itemLabel so the drop hit-region fills the entire row width, not
    /// just the Label's natural icon+text bounds. Without this, hovering on the
    /// whitespace to the right of the text doesn't trigger `isTargeted`.
    private var fullWidthLabel: some View {
        itemLabel
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
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
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
            } label: {
                fullWidthLabel
                    .draggable(item.id)
                    .dropDestination(for: String.self) { droppedIDs, _ in
                        handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                    }
                    .dropDestination(for: URL.self) { droppedURLs, _ in
                        handleExternalFileDrop(urls: droppedURLs, targetFolder: item)
                    } isTargeted: { isTargeted in
                        isDropTargeted = isTargeted
                    }
                    .contextMenu { rowContextMenu }
            }
            .listRowBackground(dropTint)
        } else if isFolder {
            fullWidthLabel
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                }
                .dropDestination(for: URL.self) { droppedURLs, _ in
                    handleExternalFileDrop(urls: droppedURLs, targetFolder: item)
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu { rowContextMenu }
                .listRowBackground(dropTint)
        } else {
            fullWidthLabel
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropBesideItem(itemIDs: droppedIDs, targetItem: item)
                }
                .dropDestination(for: URL.self) { droppedURLs, _ in
                    // Drop on a leaf file (e.g. a PDF) imports the new file into
                    // the leaf's parent folder — "drop beside" semantics, matching
                    // Finder. Non-document leaves (searches, workflows) fall
                    // through to library root.
                    handleExternalFileDrop(
                        urls: droppedURLs,
                        targetFolder: parentFolderItem(of: item)
                    )
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu { rowContextMenu }
                .listRowBackground(dropTint)
        }
    }
}
