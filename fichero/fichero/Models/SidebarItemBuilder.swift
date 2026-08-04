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

        // Add comparisons (#4335). Everything creatable in a library is a node
        // in its tree — the comparisons bucket existed (buildComparisonItems /
        // fromComparison) but was never loaded into the sidebar. History comes
        // through the library reference's ModelComparisonStore, the same
        // store-owned seam as searches/chats above.
        if FeatureManager.shared.isVisible(.modelComparison) {
            let comparisons = library.modelComparisonStore.history.map(ComparisonSummary.init)
            allItems.append(contentsOf: buildComparisonItems(from: comparisons, libraryId: library.id))
        }

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
    ///   - Every other leaf `.file` document — text/Markdown/docx/… (#4300).
    ///     Finder rule: show ALL items. Excluding generic files made a folder
    ///     of Markdown files render chevron-less and un-expandable.
    ///
    /// **Not** included in the sidebar:
    ///   - `.chunk` rows (text fragments, not user-facing nodes).
    ///
    /// NOTE: this predicate runs BEFORE the parent→children map is built, so a
    /// kind omitted here doesn't merely hide its own row — it also strips its
    /// parent's `children`. A parent built with `children == nil` still shows
    /// a chevron when the engine reported a positive `child_count` — that
    /// field IS sent on `/roots` and `/children`, contrary to the note that
    /// stood here (#4515); only the client's converter was dropping it. A
    /// kind omitted here therefore hides rows, not chevrons. Add new
    /// sidebar-visible node kinds here (#4058, #4300).
    static func isSidebarVisible(_ doc: Document) -> Bool {
        if doc.isNavigableContainer { return true }
        if doc.docType == .page { return true }
        if doc.docType == .file { return true }
        return false
    }

    /// Ids of every folder that IS the locked "Default Workflows" container or
    /// sits beneath it (#4200). Resolved once per build over ALL documents —
    /// not just the sidebar-visible ones, so an ancestor that was filtered out
    /// still resolves — because the answer is about ancestry, which a single
    /// row cannot see. A row whose ancestor isn't loaded falls back to the id
    /// fast path inside `isDefaultWorkflowFolder`.
    static func lockedSystemFolderIds(in documents: [Document]) -> Set<String> {
        let documentsById = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return Set(
            documents
                .filter { $0.isDefaultWorkflowFolder(resolveParent: { documentsById[$0] }) }
                .map(\.id)
        )
    }

    static func buildLibraryHierarchy(from documents: [Document], libraryId: UUID) -> [SidebarItem] {
        let visibleDocs = documents.filter(isSidebarVisible)

        let lockedFolderIds = lockedSystemFolderIds(in: documents)

        // Build a map of parentId -> children
        var childrenMap: [String: [Document]] = [:]
        var rootDocuments: [Document] = []
        var inboxDocument: Document?

        for doc in visibleDocs {
            if let parentId = doc.parentId {
                childrenMap[parentId, default: []].append(doc)
            } else if doc.name == "Inbox", doc.docType == .folder, inboxDocument == nil {
                // The special-cased Inbox root (#4527). The match mirrors
                // `LibraryManager.ensureInboxFolder`: name AND docType — a
                // root FILE the user happens to call "Inbox" is an ordinary
                // row, not a folder-affordanced dead end. And only the FIRST
                // match is hoisted: a duplicate root named Inbox (reachable
                // via #3970's empty-collections window) used to overwrite the
                // winner with a bare assignment and drop the loser from the
                // tree entirely — the Finder rule is show ALL items.
                inboxDocument = doc
            } else {
                rootDocuments.append(doc)
            }
        }

        // Recursively build the tree (children sorted by sequence, then name).
        // `parent` is threaded so `DocumentTitle` can use its parent-fallback
        // rung: a page whose own name is a storage filename borrows the parent
        // document's name rather than showing an upload id (#116/#4416).
        func buildItem(_ doc: Document, parent: Document? = nil) -> SidebarItem {
            let raw = childrenMap[doc.id] ?? []
            let structureChildren = buildStructureItems(for: doc, libraryId: libraryId)
            let documentChildren = raw
                .sorted(by: childOrder)
                .filter { child in
                    structureChildren.isEmpty || child.docType != .page
                }
                .map { buildItem($0, parent: doc) }
            let combined = documentChildren + structureChildren
            return SidebarItem.fromDocument(doc, libraryId: libraryId,
                                           children: combined.isEmpty ? nil : combined,
                                           isDefaultWorkflowFolder: lockedFolderIds.contains(doc.id),
                                           parent: parent)
        }

        // Build Inbox with custom icon
        func buildInboxItem(_ doc: Document) -> SidebarItem {
            let raw = childrenMap[doc.id] ?? []
            // Thread `parent` exactly as `buildItem` does for every other
            // folder (#4527): the Inbox is where storage-named imports land,
            // so its children need DocumentTitle's parent-fallback rung most
            // of all (#116/#4416).
            let children = raw.isEmpty ? nil : raw.sorted(by: childOrder).map { buildItem($0, parent: doc) }
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

        // Add other root documents, in the SAME order the backend serves them
        // (#4237). `sidebarDocuments` is `collections + childrenCache.values`,
        // so root order was pure arrival order: `/documents/roots` sorts by
        // `(sort_order, lower(name))` (`_ordered_by_sort_order`), but a live
        // `spliceDocuments` APPENDS a new root to the tail, and dictionary
        // iteration over `childrenCache` is unstable. So the row a user clicked
        // could sit at a different index moments later, once the next
        // `loadCollections()` restored backend order — selection is held by id
        // and stayed put, but the row it highlights MOVED, which reads exactly
        // as "the selection jumped up one".
        //
        // `childOrder` is the same key the backend sorts by (sortOrder, then
        // sequence, then case-insensitive name), so sorting here makes the tree
        // order a function of the documents rather than of when they arrived.
        result.append(contentsOf: rootDocuments.sorted(by: childOrder).map { buildItem($0) })

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
