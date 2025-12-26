import Foundation

/// Helper functions for building hierarchical sidebar items
enum SidebarItemBuilder {

    /// Build hierarchical library items from documents using parentId
    static func buildLibraryHierarchy(from documents: [Document]) -> [SidebarItem] {
        // Build a map of parentId -> children
        var childrenMap: [String: [Document]] = [:]
        var rootDocuments: [Document] = []

        for doc in documents {
            if let parentId = doc.parentId {
                childrenMap[parentId, default: []].append(doc)
            } else {
                rootDocuments.append(doc)
            }
        }

        // Recursively build tree
        func buildItem(_ doc: Document) -> SidebarItem {
            let children = childrenMap[doc.id]?.map { buildItem($0) }
            return SidebarItem.fromDocument(doc, children: children)
        }

        return rootDocuments.map { buildItem($0) }
    }

    /// Build hierarchical items from folderPath (for searches, chats, workflows)
    static func buildHierarchyFromPath<T>(
        items: [T],
        extractPath: (T) -> String,
        extractSortOrder: (T) -> Int,
        buildItem: (T, [SidebarItem]?) -> SidebarItem
    ) -> [SidebarItem] {
        // Group items by folder path
        var pathGroups: [String: [T]] = [:]

        for item in items {
            let path = extractPath(item)
            pathGroups[path, default: []].append(item)
        }

        // Sort items within each path by sortOrder
        for (path, items) in pathGroups {
            pathGroups[path] = items.sorted { extractSortOrder($0) < extractSortOrder($1) }
        }

        // Build tree structure
        // For now, just return flat items at root level "/"
        // In future, we can parse paths like "/folder1/subfolder" to build real hierarchy
        let rootItems = pathGroups["/"] ?? []
        return rootItems.map { buildItem($0, nil) }
    }

    /// Build hierarchical search items from saved searches
    static func buildSearchHierarchy(from searches: [SavedSearch]) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: searches,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { search, children in
                SidebarItem.fromSearch(search)
            }
        )
    }

    /// Build hierarchical chat items from conversations
    static func buildChatHierarchy(from conversations: [Conversation]) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: conversations,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { conversation, children in
                SidebarItem.fromConversation(conversation)
            }
        )
    }

    /// Build hierarchical workflow items from workflows
    static func buildWorkflowHierarchy(from workflows: [WorkflowSidebarItem]) -> [SidebarItem] {
        return buildHierarchyFromPath(
            items: workflows,
            extractPath: { $0.folderPath },
            extractSortOrder: { $0.sortOrder },
            buildItem: { workflow, children in
                SidebarItem.fromWorkflow(workflow)
            }
        )
    }
}
