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
                itemLabel
                    .draggable(item.id)
                    .dropDestination(for: String.self) { droppedIDs, _ in
                        handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                    }
                    .dropDestination(for: URL.self) { droppedURLs, _ in
                        handleExternalFileDrop(urls: droppedURLs, targetFolder: item)
                    } isTargeted: { isTargeted in
                        isDropTargeted = isTargeted
                    }
                    .contextMenu {
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
            }
        } else if isFolder {
            itemLabel
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropIntoFolder(
                        itemIDs: droppedIDs,
                        targetFolder: item
                    )
                }
                .dropDestination(for: URL.self) { droppedURLs, _ in
                    handleExternalFileDrop(urls: droppedURLs, targetFolder: item)
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
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
        } else {
            itemLabel
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropBesideItem(itemIDs: droppedIDs, targetItem: item)
                }
                .dropDestination(for: URL.self) { droppedURLs, _ in
                    handleExternalFileDrop(urls: droppedURLs, targetFolder: nil)
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
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
        }
    }
}
