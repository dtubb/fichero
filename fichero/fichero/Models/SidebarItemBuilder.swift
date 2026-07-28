import Foundation
import OSLog

private let sidebarBuilderLogger = Logger(subsystem: "app.fichero.fichero", category: "Startup")

/// Helper functions for building hierarchical sidebar items
enum SidebarItemBuilder {

    /// Build all items for a library (documents, searches, chats, workflows mixed together)
    /// Returns a flat list of items that can be children of a library header
    @MainActor
    static func buildLibraryGroup(
        library: LibraryManager.LibraryReference
    ) -> [SidebarItem] {
        let documents = library.documentStore.sidebarDocuments
        let docCount = documents.count
        sidebarBuilderLogger.info("⏱ SidebarItemBuilder.build entry — \(docCount) docs in \(library.displayName)")
        var allItems: [SidebarItem] = []

        // Add document folders first
        let libraryItems = buildLibraryHierarchy(from: documents, libraryId: library.id)
        allItems.append(contentsOf: libraryItems)

        // Add searches
        let searches = library.savedSearchService.savedSearches
        let searchItems = buildSearchHierarchy(from: searches, libraryId: library.id)
        allItems.append(contentsOf: searchItems)

        // Add chats
        let conversations = library.conversationService.conversations
        let chatItems = buildChatHierarchy(from: conversations, libraryId: library.id)
        allItems.append(contentsOf: chatItems)

        // Workflows are deliberately NOT appended here (#4186). The engine
        // mirrors every workflow into the document tree (`_save_workflow_
        // document`: presets under the locked "Default Workflows" container,
        // user workflows as normal nodes), so the mirror doc rows above ARE
        // the sidebar representation — correctly routed as regular library
        // nodes. The old client-built virtual hierarchy (grouping
        // workflow.folder_path via buildWorkflowHierarchy) DUPLICATED them
        // as unlocked folders at the tree root whose click hijacked the
        // window into the workflow surface. The workflow SURFACE (content
        // column) reads WorkflowStore directly and is unaffected.

        sidebarBuilderLogger.info("⏱ SidebarItemBuilder.build exit — \(allItems.count) total items")
        return allItems
    }

    /// Comparator for sidebar sibling docs: prefer `sequence` (PDF page order)
    /// Sort order for document siblings inside a folder (sidebar plan, #572).
    ///
    /// Priority, most to least specific:
    ///   1. User-defined `sortOrder` when the two siblings differ — the
    ///      backend's `/documents/reorder` route assigns these sequentially
    ///      so lower means earlier. A folder whose documents have never
    ///      been reordered has every doc at `sortOrder == 0`; in that case
    ///      the comparison ties and falls through to the next key.
    ///   2. `sequence` on PDF page children (keeps page order stable).
    ///   3. Case-insensitive name.
    static func childOrder(_ lhs: Document, _ rhs: Document) -> Bool {
        if lhs.sortOrder != rhs.sortOrder {
            return lhs.sortOrder < rhs.sortOrder
        }
        if let lSeq = lhs.sequence, let rSeq = rhs.sequence {
            return lSeq < rSeq
        }
        return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
    }

    /// Build hierarchical library items from documents using parentId.
    ///
    /// Included in the sidebar:
    ///   - Folders (navigation containers)
    ///   - PDFs (first-class containers per #568)
    ///   - Image files and page documents as leaf rows under their parent folder/PDF
    ///   - Structured PDF outline rows; when an outline exists, it still replaces
    ///     flat page rows for now pending the chapter-vs-page product decision (#3172).
    ///   - Workflow mirror nodes, the engine-side rows under "Default Workflows"
    ///     (#4058) — `.file` docs with no `fileType`, so without an explicit
    ///     case they were filtered out and took their container's chevron too.
    ///
    /// **Not** included in the sidebar:
    ///   - Text/docx/other generic files — stay in the main grid only.
    ///
    /// The sidebar is for containers, one level of drill-in at a time, like
    /// Finder.
    ///
    /// NOTE: this predicate runs BEFORE the parent→children map is built, so a
    /// kind omitted here doesn't merely hide its own row — it also strips its
    /// parent's `children`, and a parent built with `children == nil` reports
    /// `isExpandable == false` (the backend sends no `child_count` on
    /// `getRoots`/`getChildren`) so it renders with no disclosure chevron at
    /// all. Add new sidebar-visible node kinds here (#4058).
    static func isSidebarVisible(_ doc: Document) -> Bool {
        if doc.isNavigableContainer { return true }
        if doc.docType == .page { return true }
        if doc.fileType == .image { return true }
        if doc.isWorkflowNode { return true }
        return false
    }

    static func buildLibraryHierarchy(from documents: [Document], libraryId: UUID) -> [SidebarItem] {
        let visibleDocs = documents.filter(isSidebarVisible)

        // Build a map of parentId -> children
        var childrenMap: [String: [Document]] = [:]
        var rootDocuments: [Document] = []
        var inboxDocument: Document?

        for doc in visibleDocs {
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

        // Recursively build the tree (children sorted by sequence, then name).
        func buildItem(_ doc: Document) -> SidebarItem {
            let raw = childrenMap[doc.id] ?? []
            let structureChildren = buildStructureItems(for: doc, libraryId: libraryId)
            let documentChildren = raw
                .sorted(by: childOrder)
                .filter { child in
                    structureChildren.isEmpty || child.docType != .page
                }
                .map { buildItem($0) }
            let combined = documentChildren + structureChildren
            return SidebarItem.fromDocument(doc, libraryId: libraryId, children: combined.isEmpty ? nil : combined)
        }

        // Build Inbox with custom icon
        func buildInboxItem(_ doc: Document) -> SidebarItem {
            let raw = childrenMap[doc.id] ?? []
            let children = raw.isEmpty ? nil : raw.sorted(by: childOrder).map { buildItem($0) }
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

    private static func buildStructureItems(
        for doc: Document,
        libraryId: UUID
    ) -> [SidebarItem] {
        guard doc.fileType == .pdf, !doc.structure.isEmpty else {
            return []
        }
        return doc.structure.map { structureItem($0, documentId: doc.id, libraryId: libraryId) }
    }

    private static func structureItem(
        _ node: DocumentStructureNode,
        documentId: String,
        libraryId: UUID
    ) -> SidebarItem {
        let children = node.children.map {
            structureItem($0, documentId: documentId, libraryId: libraryId)
        }
        let pageRange = "\(node.pageRange.start)-\(node.pageRange.end)"
        return SidebarItem(
            id: "structure:\(documentId):\(node.id)",
            name: "\(node.title)  p. \(pageRange)",
            icon: structureIcon(for: node.kind),
            category: .folder,
            itemType: .folder(folderPath: "structure/\(documentId)/\(node.id)"),
            children: children.isEmpty ? nil : children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "structure/\(documentId)",
            sortOrder: node.pageRange.start,
            isFolder: !children.isEmpty
        )
    }

    private static func structureIcon(for kind: String) -> String {
        switch kind {
        case "chapter": return "book.closed"
        case "section": return "text.book.closed"
        case "subsection": return "list.bullet.indent"
        default: return "text.alignleft"
        }
    }

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
