import Foundation

/// Helper functions for building hierarchical sidebar items
enum SidebarItemBuilder {

    /// Build all items for a library (documents, searches, chats, workflows mixed together)
    /// Returns a flat list of items that can be children of a library header
    @MainActor
    static func buildLibraryGroup(
        library: LibraryManager.LibraryReference
    ) -> [SidebarItem] {
        var allItems: [SidebarItem] = []

        // Add document folders first
        let documents = library.documentStore.collections
        let libraryItems = buildLibraryHierarchy(from: documents, libraryId: library.id)
        allItems.append(contentsOf: libraryItems)

        // Add searches
        let searches = library.savedSearchServiceGenerated.savedSearches
        let searchItems = buildSearchHierarchy(from: searches, libraryId: library.id)
        allItems.append(contentsOf: searchItems)

        // Add chats
        let conversations = library.conversationServiceGenerated.conversations
        let chatItems = buildChatHierarchy(from: conversations, libraryId: library.id)
        allItems.append(contentsOf: chatItems)

        // Add workflows (already WorkflowSidebarItems in WorkflowStore)
        let workflows = library.workflowStore.workflows
        let workflowItems = buildWorkflowHierarchy(from: workflows, libraryId: library.id)
        allItems.append(contentsOf: workflowItems)

        return allItems
    }

    /// Build hierarchical library items from documents using parentId
    static func buildLibraryHierarchy(from documents: [Document], libraryId: UUID) -> [SidebarItem] {
        // Only show folders in the sidebar, not individual files
        let folders = documents.filter { $0.docType == .folder }

        // Build a map of parentId -> children (folders only)
        var childrenMap: [String: [Document]] = [:]
        var rootDocuments: [Document] = []
        var inboxDocument: Document?

        for doc in folders {
            if let parentId = doc.parentId {
                childrenMap[parentId, default: []].append(doc)
            } else {
                // Check if this is the Inbox folder
                if doc.name == "Inbox" {
                    inboxDocument = doc
                } else {
                    rootDocuments.append(doc)
                }
            }
        }

        // Recursively build tree (only folders)
        func buildItem(_ doc: Document) -> SidebarItem {
            let children = childrenMap[doc.id]?.map { buildItem($0) }
            return SidebarItem.fromDocument(doc, libraryId: libraryId, children: children)
        }

        // Build Inbox with custom icon
        func buildInboxItem(_ doc: Document) -> SidebarItem {
            let children = childrenMap[doc.id]?.map { buildItem($0) }
            return SidebarItem(
                id: "doc:\(doc.id)",
                name: doc.name,
                icon: "tray.fill",  // Special inbox icon
                category: .folder,
                itemType: .document(doc),
                children: children,
                progress: nil,
                showProgress: false,
                libraryId: libraryId,
                folderPath: doc.parentId ?? "/",
                sortOrder: 0,
                isFolder: true
            )
        }

        var result: [SidebarItem] = []

        // Add Inbox first with special icon
        if let inbox = inboxDocument {
            result.append(buildInboxItem(inbox))
        }

        // Add other root documents
        result.append(contentsOf: rootDocuments.map { buildItem($0) })

        return result
    }

    /// Build hierarchical items from folderPath (for searches, chats, workflows)
    // swiftlint:disable:next function_parameter_count
    static func buildHierarchyFromPath<T>(
        items: [T],
        libraryId: UUID,
        extractPath: (T) -> String,
        extractSortOrder: (T) -> Int,
        buildItem: (T, [SidebarItem]?) -> SidebarItem,
        category: ItemCategory
    ) -> [SidebarItem] {
        // Group items by folder path
        let pathGroups = Dictionary(grouping: items, by: extractPath)

        // Find all unique folder paths and create folder items
        var folderItems: [String: SidebarItem] = [:]
        let allPaths = Set(items.map(extractPath))

        for path in allPaths where path != "/" {
            createFolderItems(for: path, category: category, libraryId: libraryId, folderItems: &folderItems)
        }

        // Build tree recursively starting from root
        return buildSubtree(
            folderPath: "/",
            pathGroups: pathGroups,
            folderItems: folderItems,
            extractSortOrder: extractSortOrder,
            buildItem: buildItem
        )
    }

    /// Create folder items for a path and all its parent paths
    private static func createFolderItems(
        for path: String,
        category: ItemCategory,
        libraryId: UUID,
        folderItems: inout [String: SidebarItem]
    ) {
        guard path != "/" && !folderItems.keys.contains(path) else { return }

        // Extract folder name from path
        let components = path.split(separator: "/")
        guard let lastComponent = components.last else { return }
        let folderName = String(lastComponent)

        // Create folder item
        folderItems[path] = SidebarItem.folder(
            name: folderName,
            folderPath: path,
            category: category,
            libraryId: libraryId,
            children: nil
        )

        // Recursively create parent folders
        let parentPath = parentFolderPath(of: path)
        if parentPath != "/" {
            createFolderItems(for: parentPath, category: category, libraryId: libraryId, folderItems: &folderItems)
        }
    }

    /// Build a subtree for a specific folder path
    private static func buildSubtree<T>(
        folderPath: String,
        pathGroups: [String: [T]],
        folderItems: [String: SidebarItem],
        extractSortOrder: (T) -> Int,
        buildItem: (T, [SidebarItem]?) -> SidebarItem
    ) -> [SidebarItem] {
        var result: [SidebarItem] = []

        // Add items directly in this folder
        if let itemsInFolder = pathGroups[folderPath] {
            let sortedItems = itemsInFolder.sorted { extractSortOrder($0) < extractSortOrder($1) }
            result.append(contentsOf: sortedItems.map { buildItem($0, nil) })
        }

        // Add child folders with their contents
        let childFolders = folderItems.values
            .filter { parentFolderPath(of: $0.folderPath) == folderPath }
            .sorted { $0.name < $1.name }

        for folder in childFolders {
            // Recursively build children for this folder
            let children = buildSubtree(
                folderPath: folder.folderPath,
                pathGroups: pathGroups,
                folderItems: folderItems,
                extractSortOrder: extractSortOrder,
                buildItem: buildItem
            )

            // Update folder with children
            var updatedFolder = folder
            updatedFolder.children = children.isEmpty ? nil : children
            result.append(updatedFolder)
        }

        return result
    }

    /// Get the parent folder path of a given path
    private static func parentFolderPath(of path: String) -> String {
        guard path != "/" else { return "/" }

        let components = path.split(separator: "/")
        guard components.count > 1 else { return "/" }

        let parentComponents = components.dropLast()
        return parentComponents.isEmpty ? "/" : "/" + parentComponents.joined(separator: "/")
    }

    /// Build hierarchical search items from saved searches
    static func buildSearchHierarchy(from searches: [SavedSearch], libraryId: UUID) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: searches,
            libraryId: libraryId,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { search, _ in
                SidebarItem.fromSearch(search, libraryId: libraryId)
            },
            category: .search
        )
    }

    /// Build hierarchical chat items from conversations
    static func buildChatHierarchy(from conversations: [Conversation], libraryId: UUID) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: conversations,
            libraryId: libraryId,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { conversation, _ in
                SidebarItem.fromConversation(conversation, libraryId: libraryId)
            },
            category: .chat
        )
    }

    /// Build hierarchical workflow items from workflows
    static func buildWorkflowHierarchy(from workflows: [WorkflowSidebarItem], libraryId: UUID) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: workflows,
            libraryId: libraryId,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { workflow, _ in
                SidebarItem.fromWorkflow(workflow, libraryId: libraryId)
            },
            category: .workflow
        )
    }

    /// Build chain items with folder hierarchy
    static func buildChainItems(from chains: [WorkflowChain], libraryId: UUID) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: chains,
            libraryId: libraryId,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { chain, _ in
                SidebarItem.fromChain(chain, libraryId: libraryId)
            },
            category: .workflow  // Chains use same category as workflows
        )
    }

    /// Build comparison items (flat list)
    static func buildComparisonItems(from comparisons: [ComparisonSummary], libraryId: UUID) -> [SidebarItem] {
        comparisons.map { SidebarItem.fromComparison($0, libraryId: libraryId) }
    }

    /// Build schedule items (flat list - schedules don't have folder paths)
    static func buildScheduleItems(from schedules: [ScheduleInfo], libraryId: UUID) -> [SidebarItem] {
        schedules.map { SidebarItem.fromSchedule($0, libraryId: libraryId) }
    }

    /// Build trigger items (flat list)
    static func buildTriggerItems(from triggers: [TriggerInfo], libraryId: UUID) -> [SidebarItem] {
        triggers.map { SidebarItem.fromTrigger($0, libraryId: libraryId) }
    }

    /// Build batch items (flat list)
    static func buildBatchItems(from batches: [BatchInfo], libraryId: UUID) -> [SidebarItem] {
        batches.map { SidebarItem.fromBatch($0, libraryId: libraryId) }
    }

    /// Build activity items (flat list)
    static func buildActivityItems(from activities: [ActivityItem], libraryId: UUID) -> [SidebarItem] {
        activities.map { SidebarItem.fromActivityRun($0, libraryId: libraryId) }
    }
}
