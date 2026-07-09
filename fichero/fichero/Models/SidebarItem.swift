import Foundation

// MARK: - Sidebar Structure

/// Category of sidebar item (for icon/display purposes)
enum ItemCategory: String, CaseIterable, Identifiable {
    case folder = "Folder"
    case search = "Search"
    case chat = "Chat"
    case workflow = "Workflow"
    case automation = "Automation"  // Schedules and triggers
    case batch = "Batch"  // Running batches
    case activity = "Activity"  // Workflow runs
    case library = "Library"  // For library group headers

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .search: return "magnifyingglass"
        case .chat: return "bubble.left.and.bubble.right"
        case .workflow: return "arrow.triangle.branch"
        case .automation: return "clock.arrow.2.circlepath"
        case .batch: return "square.stack.3d.up"
        case .activity: return "waveform.path.ecg"
        case .library: return "book.closed"
        }
    }
}

/// Generic sidebar item that can be a document, search, chat, or workflow
/// In library-grouped mode, items from all categories can be siblings within a library
struct SidebarItem: Identifiable, Hashable {
    let id: String
    let name: String
    let icon: String
    let category: ItemCategory
    let itemType: ItemType
    var children: [SidebarItem]?
    var progress: Double?  // Optional progress indicator (0.0 to 1.0)
    var showProgress: Bool = false  // Whether to show the progress indicator

    // Multi-library support
    let libraryId: UUID?  // Which library this item belongs to (nil for library group headers)

    // Hierarchical support
    let folderPath: String  // Unix-style path: "/archive/letters"
    let sortOrder: Int      // User-defined order within folder
    let isFolder: Bool      // True for folder items, false for leaf items

    enum ItemType: Hashable {
        case document(Document)
        case savedSearch(SavedSearch)
        case conversation(Conversation)
        case workflow(WorkflowSidebarItem)
        case chain(WorkflowChain)
        case comparison(ComparisonSummary)
        case schedule(ScheduleInfo)
        case trigger(TriggerInfo)
        case batch(BatchInfo)
        case activityRun(ActivityItem)
        case folder(folderPath: String)  // Folder item (no data, just structure)
        case libraryHeader  // For library group headers
    }

    var isExpandable: Bool {
        if let children, !children.isEmpty {
            return true
        }
        guard case .document(let document) = itemType else { return false }
        if !document.structure.isEmpty {
            return true
        }
        return document.isNavigableContainer && document.childCount > 0
    }

    var destination: SidebarDestination {
        SidebarDestination(serializedID: id) ?? .document(id)
    }

    /// What kind of items can this item accept as drop targets, if any?
    ///
    /// Returns:
    /// - `.document` for document folders (real `.folder` docType with a
    ///   backing `Document` record).
    /// - `.savedSearch` / `.conversation` / `.workflow` for virtual folders
    ///   in the corresponding sections (type is `.folder(folderPath:)`,
    ///   category distinguishes which section owns the folder).
    /// - `nil` for everything else (leaves, library headers, non-folder
    ///   items) — the drop handler uses that to reject the drop.
    ///
    /// Used by `SidebarItemRow+DropHandlers.swift:handleDropIntoFolder` to
    /// decide whether a drop on this item is valid and which backend
    /// service to call for the move. Sidebar plan Step 9 (#585).
    var folderKind: SidebarItemKind? {
        switch itemType {
        case .document(let doc) where doc.docType == .folder:
            return .document
        case .folder:
            switch category {
            case .search: return .savedSearch
            case .chat: return .conversation
            case .workflow: return .workflow
            default: return nil
            }
        default:
            return nil
        }
    }

    // Convenience initializers
    static func fromDocument(_ doc: Document, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "doc:\(doc.id)",
            name: doc.pageThumbnailLabel ?? doc.name,
            // Prefer the file-type-specific icon (e.g. "doc.richtext" for PDFs)
            // over the generic docType icon ("doc" for any .file) — makes
            // PDFs visually distinct in the sidebar (#574).
            icon: doc.fileType?.icon ?? doc.docType.icon,
            category: .folder,
            itemType: .document(doc),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: doc.parentId ?? "/",  // Documents use parentId for hierarchy
            sortOrder: doc.sortOrder,  // backed by backend /documents/reorder (#572)
            isFolder: doc.docType == .folder
        )
    }

    static func fromSearch(_ search: SavedSearch, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "search:\(search.id)",
            name: search.name,
            icon: search.icon,
            category: .search,
            itemType: .savedSearch(search),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: search.folderPath,
            sortOrder: search.sortOrder,
            isFolder: false
        )
    }

    static func fromWorkflow(
        _ workflow: WorkflowSidebarItem,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "workflow:\(workflow.id)",
            name: workflow.name,
            icon: "arrow.triangle.branch",
            category: .workflow,
            itemType: .workflow(workflow),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: workflow.folderPath,
            sortOrder: workflow.sortOrder,
            isFolder: false
        )
    }

    static func fromConversation(
        _ conversation: Conversation,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "chat:\(conversation.id)",
            name: conversation.title,
            icon: "bubble.left.and.bubble.right",
            category: .chat,
            itemType: .conversation(conversation),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: conversation.folderPath,
            sortOrder: conversation.sortOrder,
            isFolder: false
        )
    }

    // Create a folder item
    static func folder(
        name: String,
        folderPath: String,
        category: ItemCategory,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "folder:\(folderPath):\(category.rawValue)",
            name: name,
            icon: "folder",
            category: category,
            itemType: .folder(folderPath: folderPath),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: folderPath,
            sortOrder: 0,
            isFolder: true
        )
    }

    // Create a library group header (top-level library item)
    @MainActor
    static func libraryHeader(
        library: LibraryManager.LibraryReference,
        children: [SidebarItem]
    ) -> SidebarItem {
        SidebarItem(
            id: "library:\(library.id.uuidString)",
            name: library.displayName,
            icon: "book.closed",
            category: .library,
            itemType: .libraryHeader,
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: library.id,  // Library headers have their own ID
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }
}
