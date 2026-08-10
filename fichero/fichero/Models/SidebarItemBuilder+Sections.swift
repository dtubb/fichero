import Foundation

// Path-based hierarchy assembly and the per-section builders (searches,
// chats, workflows, chains, comparisons, schedules, triggers, batches,
// activity). Split from SidebarItemBuilder.swift for the file/type-length
// lint budgets — same enum, same access, no behavior change.
extension SidebarItemBuilder {

    // Build hierarchical items from folderPath (for searches, chats, workflows)
    // swiftlint:disable:next function_parameter_count
    static func buildHierarchyFromPath<T>(
        items: [T],
        libraryId: UUID,
        extractPath: (T) -> String,
        extractSortOrder: (T) -> Int,
        buildItem: (T, [SidebarItem]?) -> SidebarItem,
        category: ItemCategory
    ) -> [SidebarItem] {
        // Group items by NORMALISED folder path (#4528). `folder_path` is a
        // plain server string: "" is one bad write away, and "/archive/" vs
        // "/archive" used to be two distinct dictionary keys — the walker
        // starts at "/" and only visits materialised folders, so the empty
        // path VANISHED a row and the trailing slash rendered one folder
        // twice with its contents split.
        let normalizedPath: (T) -> String = { normalizedFolderPath(extractPath($0)) }
        let pathGroups = Dictionary(grouping: items, by: normalizedPath)

        // Find all unique folder paths and create folder items
        var folderItems: [String: SidebarItem] = [:]
        let allPaths = Set(items.map(normalizedPath))

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

        // Add child folders with their contents. Sibling folders order by the
        // SAME comparator sibling documents use (`childOrder`'s name rung,
        // #4528) — a raw `<` put every lowercase name after every uppercase
        // one, and the same two names ordered differently per section.
        let childFolders = folderItems.values
            .filter { parentFolderPath(of: $0.folderPath) == folderPath }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }

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

    /// One canonical spelling per folder path (#4528): split into components
    /// and rejoin, so "", "/", "/archive/" and "//archive" all land on the
    /// same key `parentFolderPath` computes with the same component logic.
    private static func normalizedFolderPath(_ path: String) -> String {
        let components = path.split(separator: "/")
        return components.isEmpty ? "/" : "/" + components.joined(separator: "/")
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
// buildWorkflowHierarchy deleted (views audit 2026-08-10): the dormant
    // re-entry point for the #4186 duplicate client-side workflow hierarchy —
    // workflows reach the tree as engine-mirrored document nodes.

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
