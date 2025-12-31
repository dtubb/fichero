import SwiftUI
import UniformTypeIdentifiers
import OSLog

/// Structured logger for sidebar row operations.
private let logger = Logger(subsystem: "com.fichero.app", category: "SidebarRow")

/// Individual row for sidebar items.
///
/// Displays hierarchical content using `DisclosureGroup` and handles:
/// - Inline rename with `TextField`
/// - Drag & drop operations (into folders, beside items, to root)
/// - Context menus for item actions
///
/// Uses `@EnvironmentObject` pattern to access shared services, following Apple's
/// recommended practice from the Food Truck sample instead of passing 9 parameters.
///
/// - Note: This view recursively renders child items for folders.
struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager

    // Access shared services via environment (reduces 9 parameters → 5)
    @EnvironmentObject private var services: SidebarServices

    // Convenience accessors for services
    private var documentStore: DocumentStore? { services.documentStore }
    private var savedSearchService: SavedSearchService? { services.savedSearchService }
    private var conversationService: ConversationService? { services.conversationService }
    private var workflowStore: WorkflowStore? { services.workflowStore }

    @State private var isDropTargeted = false
    @FocusState private var isRenameFocused: Bool
    @State private var isCommittingRename = false

    /// Determines if this item represents a folder type document.
    private var isFolder: Bool {
        guard case .document(let doc) = item.itemType else { return false }
        return doc.docType == .folder
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
                        renameState: renameState,
                        deleteState: deleteState
                    )
                    .tag(child.id)
                    // No context menu here - child SidebarItemRow renders its own
                }
            } label: {
                itemLabel
                    .listRowBackground(
                        isDropTargeted
                            ? Color.accentColor.opacity(SidebarConstants.dropTargetOpacity)
                            : Color.clear
                    )
                    .draggable(item.id)
                    .dropDestination(for: String.self) { droppedIDs, _ in
                        handleDropIntoFolder(itemIDs: droppedIDs, targetFolder: item)
                    } isTargeted: { isTargeted in
                        isDropTargeted = isTargeted
                    }
                    .contextMenu {
                        SidebarItemContextMenu(
                            item: item,
                            renameState: renameState,
                            deleteState: deleteState
                        )
                    }
            }
        } else if isFolder {
            // Empty folder - still needs to accept drops
            itemLabel
                .listRowBackground(
                    isDropTargeted ? Color.accentColor.opacity(SidebarConstants.dropTargetOpacity) : Color.clear
                )
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropIntoFolder(
                        itemIDs: droppedIDs,
                        targetFolder: item
                    )
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState
                    )
                }
        } else {
            // Regular document - can be dragged and can accept drops to become siblings
            itemLabel
                .listRowBackground(
                    isDropTargeted
                        ? Color.accentColor.opacity(SidebarConstants.dropTargetNonFolderOpacity)
                        : Color.clear
                )
                .draggable(item.id)
                .dropDestination(for: String.self) { droppedIDs, _ in
                    handleDropBesideItem(itemIDs: droppedIDs, targetItem: item)
                } isTargeted: { isTargeted in
                    isDropTargeted = isTargeted
                }
                .contextMenu {
                    SidebarItemContextMenu(
                        item: item,
                        renameState: renameState,
                        deleteState: deleteState
                    )
                }
        }
    }

    // MARK: - Item Label

    /// Label with name (text or rename field) and icon.
    ///
    /// Shows TextField when this specific row is being renamed, otherwise shows static Text.
    /// The condition check happens for every row on state changes, but only one TextField
    /// is actually created.
    private var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
            }
        } icon: {
            Image(systemName: item.icon)
                .foregroundColor(iconColor)
        }
    }

    /// TextField for inline renaming with focus management and validation.
    private var renameField: some View {
        TextField("Name", text: $renameState.editingName)
            .textFieldStyle(.plain)
            .focused($isRenameFocused)
            .lineLimit(1)
            .truncationMode(.tail)
            .onSubmit {
                commitRename()
            }
            .onExitCommand {
                renameState.cancelRename()
                isRenameFocused = false
            }
            .onChange(of: isRenameFocused) { _, newValue in
                if !newValue && renameState.renamingItemId == item.id && !isCommittingRename {
                    // Focus was lost without submitting, cancel rename
                    renameState.cancelRename()
                }
            }
            .task {
                // Automatically focus the TextField when rename starts
                isRenameFocused = true
            }
    }

    private var iconColor: Color {
        switch item.section {
        case .library:
            return .accentColor
        case .searches:
            return .orange
        case .chat:
            return .green
        case .workflows:
            return .purple
        }
    }
}

// MARK: - Drag & Drop Operations

extension SidebarItemRow {
    func handleDropBesideItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        logger.debug(" ========== DROP BESIDE STARTED ==========")
        logger.debug(" handleDropBesideItem called with \(itemIDs.count) items beside \(targetItem.name)")

        // Get the target item's parent (to make dropped items siblings of target)
        let targetParentId: String?
        if case .document(let targetDoc) = targetItem.itemType {
            targetParentId = targetDoc.parentId
            logger.debug(" Target parent ID: \(targetParentId ?? "root")")
        } else {
            logger.debug(" ⚠️ Target item is not a document, cannot determine parent")
            return false
        }

        // Move each dropped item to the same parent as the target
        for itemID in itemIDs {
            logger.debug(" Moving item \(itemID) to be sibling of \(targetItem.name)")

            // Prevent dropping item onto itself
            guard itemID != targetItem.id else {
                logger.debug(" ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            Task {
                if let parentId = targetParentId {
                    await moveItemToFolder(itemId: itemID, targetFolderId: parentId)
                } else {
                    // Move to root by setting parent to nil
                    let actualItemId = extractActualId(from: itemID)
                    guard let documentStore = documentStore else { return }
                    do {
                        _ = try await documentStore.moveDocument(actualItemId, toParent: nil)
                        logger.debug(" ✅ Move to root successful")
                    } catch {
                        logger.debug(" ❌ Move to root failed: \(error.localizedDescription)")
                    }
                }
            }
        }

        logger.debug(" ========== DROP BESIDE COMPLETED ==========")
        return true
    }

    func handleDropIntoFolder(itemIDs: [String], targetFolder: SidebarItem) -> Bool {
        logger.debug(" ========== DROP STARTED ==========")
        logger.debug(" handleDropIntoFolder called with \(itemIDs.count) items onto \(targetFolder.name)")
        logger.debug("Item IDs: \(itemIDs)")
        logger.debug("Target folder ID: \(targetFolder.id)")
        logger.debug("Target folder itemType: \(String(describing: targetFolder.itemType))")

        // Validate that target is actually a folder
        guard case .document(let targetDoc) = targetFolder.itemType,
              targetDoc.docType == .folder else {
            logger.warning("❌ Drop rejected: target \(targetFolder.name) is not a folder")
            return false
        }

        logger.debug("Target \(targetFolder.name) is valid folder (docType: \(String(describing: targetDoc.docType)))")
        logger.debug("Target document ID from doc: \(targetDoc.id)")

        // Move each dropped item
        for itemID in itemIDs {
            logger.debug(" Processing drop of item ID: \(itemID)")

            // Prevent dropping item onto itself
            guard itemID != targetFolder.id else {
                logger.debug(" ⚠️ Drop rejected: cannot drop item onto itself")
                continue
            }

            // Validate circular reference: cannot drop folder into its own child
            if isDescendant(targetFolder.id, of: itemID) {
                logger.debug(" ⚠️ Drop rejected: circular reference detected")
                continue
            }

            // Call backend to update parent
            logger.debug(" ✅ Validation passed, calling moveItemToFolder")
            logger.debug("    Source ID: \(itemID)")
            logger.debug("    Target ID: \(targetFolder.id)")
            Task {
                await moveItemToFolder(itemId: itemID, targetFolderId: targetFolder.id)
            }
        }
        logger.debug(" ========== DROP COMPLETED ==========")
        return true
    }

    func handleDropOntoItem(itemIDs: [String], targetItem: SidebarItem) -> Bool {
        // For non-folder items, we don't support dropping onto them
        logger.debug(" Drop onto non-folder item not supported")
        return false
    }
}

// MARK: - Helper Functions

extension SidebarItemRow {
    func isDescendant(_ potentialDescendant: String, of ancestorId: String) -> Bool {
        // Check if potentialDescendant is a child/grandchild/etc of ancestorId
        // This prevents circular references (e.g., dragging a folder into its own child)

        // Find the ancestor item in cached items
        guard let ancestorItem = findItemById(ancestorId, in: allCachedItems) else {
            return false
        }

        // Recursively check if potentialDescendant is in ancestorItem's children tree
        return containsDescendant(potentialDescendant, in: ancestorItem)
    }

    func findItemById(_ id: String, in items: [SidebarItem]) -> SidebarItem? {
        for item in items {
            if item.id == id {
                return item
            }
            if let children = item.children,
               let found = findItemById(id, in: children) {
                return found
            }
        }
        return nil
    }

    func containsDescendant(_ targetId: String, in item: SidebarItem) -> Bool {
        // Check if this item is the target
        if item.id == targetId {
            return true
        }

        // Recursively check children
        if let children = item.children {
            for child in children where containsDescendant(targetId, in: child) {
                return true
            }
        }

        return false
    }

    func extractActualId(from prefixedId: String) -> String {
        if prefixedId.contains(":") {
            return String(prefixedId.split(separator: ":")[1])
        }
        return prefixedId
    }

    func moveItemToFolder(itemId: String, targetFolderId: String) async {
        logger.debug(" moveItemToFolder: \(itemId) → \(targetFolderId)")

        guard let documentStore = documentStore else { return }

        // Extract actual IDs (strip prefix like "doc:")
        let actualItemId = extractActualId(from: itemId)
        let actualTargetId = extractActualId(from: targetFolderId)

        do {
            // Use documentStore (same pattern as rename/delete) - no refresh() needed!
            _ = try await documentStore.moveDocument(actualItemId, toParent: actualTargetId)
            logger.debug(" ✅ Move successful - UI updates automatically via @Published")

        } catch {
            logger.debug(" ❌ Move failed: \(error.localizedDescription)")
        }
    }
}

// MARK: - Rename Operations

extension SidebarItemRow {
    func commitRename() {
        let newName = renameState.editingName.trimmingCharacters(in: .whitespacesAndNewlines)

        // CRITICAL: Use renamingItemId from renameState, NOT item.id
        // item.id might be wrong in nested hierarchies due to recursive rendering
        guard let itemIdToRename = renameState.renamingItemId else {
            logger.warning("commitRename called but no item is being renamed")
            renameState.cancelRename()
            return
        }

        logger.debug("Committing rename for item ID: \(itemIdToRename), new name: \(newName)")
        logger.debug("  - Current row's item: \(item.name) (id: \(item.id))")
        logger.debug("  - renameState.renamingItemId: \(itemIdToRename)")

        // Validate name
        guard !newName.isEmpty else {
            renameState.cancelRename()
            return
        }

        guard newName.count <= SidebarConstants.maxNameLength else {
            renameState.cancelRename()
            return
        }

        // Mark that we're committing to prevent onChange from canceling
        isCommittingRename = true

        // Call backend to rename - use the ID from renameState, not item.id!
        Task {
            await performRename(itemId: itemIdToRename, newName: newName)
            await MainActor.run {
                renameState.cancelRename()
                isCommittingRename = false
            }
        }
    }

    func performRename(itemId: String, newName: String) async {
        logger.debug("performRename called with itemId: \(itemId), newName: \(newName)")
        logger.debug("  - Current row's item: \(item.name) (id: \(item.id))")

        // CRITICAL: Find the actual item being renamed from allCachedItems
        // Don't use `item` from current row - it might be wrong due to recursive rendering
        guard let itemToRename = findItemById(itemId, in: allCachedItems) else {
            logger.warning("⚠️ Could not find item with ID \(itemId) in cached items")
            return
        }

        logger.debug("  - Found item to rename: \(itemToRename.name) (id: \(itemToRename.id))")

        // For document items, use DocumentStore which updates local state properly
        if case .document(let document) = itemToRename.itemType {
            await renameDocument(document, to: newName)
        } else {
            await renameNonDocumentItem(itemToRename, itemId: itemId, newName: newName)
        }
    }

    func renameDocument(_ document: Document, to newName: String) async {
        logger.debug("  - Renaming document: \(document.name) (id: \(document.id))")
        guard let documentStore = documentStore else { return }
        do {
            let updated = try await documentStore.renameDocument(document, to: newName)
            logger.debug(" Renamed document to '\(updated.name)'")
            // DocumentStore.renameDocument already updates @Published collections
            // SwiftUI will automatically rebuild the tree and maintain selection via ID
            // No manual restoration needed!
        } catch {
            logger.debug(" Failed to rename document: \(error.localizedDescription)")
        }
    }

    func renameNonDocumentItem(
        _ itemToRename: SidebarItem,
        itemId: String,
        newName: String
    ) async {
        // For non-document items (searches, chats, workflows)
        let actualId: String
        if itemId.contains(":") {
            actualId = String(itemId.split(separator: ":")[1])
        } else {
            actualId = itemId
        }

        do {
            // Use the correct service based on item type
            switch itemToRename.itemType {
            case .savedSearch:
                guard let savedSearchService = savedSearchService else { return }
                _ = try await savedSearchService.renameSavedSearch(actualId, newName: newName)
                logger.debug(" Renamed saved search \(actualId) to '\(newName)'")
            case .conversation:
                guard let conversationService = conversationService else { return }
                _ = try await conversationService.renameConversation(actualId, newTitle: newName)
                logger.debug(" Renamed conversation \(actualId) to '\(newName)'")
            case .workflow:
                guard let workflowStore = workflowStore else { return }
                _ = try await workflowStore.renameWorkflow(actualId, to: newName)
                logger.debug(" Renamed workflow \(actualId) to '\(newName)'")
            default:
                logger.debug(" ⚠️ Unknown item type for rename")
            }
            // UI updates automatically via @Published collections
        } catch {
            logger.debug(" Failed to rename item: \(error.localizedDescription)")
        }
    }
}
