import Foundation

// MARK: - Sidebar Structure

/// Category of sidebar item (for icon/display purposes)
enum ItemCategory: String, CaseIterable, Identifiable {
    case folder = "Folder"
    case search = "Search"
    case chat = "Chat"
    case workflow = "Workflow"
    case library = "Library"  // For library group headers

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .search: return "magnifyingglass"
        case .chat: return "bubble.left.and.bubble.right"
        case .workflow: return "arrow.triangle.branch"
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
        case folder(folderPath: String)  // Folder item (no data, just structure)
        case libraryHeader  // For library group headers
    }

    var isExpandable: Bool {
        children != nil && !children!.isEmpty
    }

    // Convenience initializers
    static func fromDocument(_ doc: Document, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "doc:\(doc.id)",
            name: doc.name,
            icon: doc.docType.icon,
            category: .folder,
            itemType: .document(doc),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: doc.parentId ?? "/",  // Documents use parentId for hierarchy
            sortOrder: 0,  // Documents don't have sort_order (yet)
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

    static func fromWorkflow(_ workflow: WorkflowSidebarItem, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
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

    static func fromConversation(_ conversation: Conversation, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
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

// MARK: - Conversation (for RAG Chat)

struct Conversation: Identifiable, Codable, Hashable {
    let id: String
    var title: String
    var messages: [ChatMessage]
    var documentScope: [String]  // Document IDs to search within
    var folderPath: String
    var sortOrder: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case messages
        case documentScope = "document_ids"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(
        id: String = UUID().uuidString,
        title: String = "New Chat",
        messages: [ChatMessage] = [],
        documentScope: [String] = [],
        folderPath: String = "/",
        sortOrder: Int = 0,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.messages = messages
        self.documentScope = documentScope
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

struct ChatMessage: Identifiable, Codable, Hashable {
    let id: String
    var role: ChatRole
    var content: String
    var sources: [DocumentSource]?
    var timestamp: Date

    init(
        id: String = UUID().uuidString,
        role: ChatRole,
        content: String,
        sources: [DocumentSource]? = nil,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.sources = sources
        self.timestamp = timestamp
    }
}

enum ChatRole: String, Codable, Hashable {
    case user
    case assistant
    case system
}

struct DocumentSource: Identifiable, Codable, Hashable {
    let id: String
    let documentId: String
    let documentName: String
    let excerpt: String
    let relevanceScore: Double
}

// MARK: - Saved Search

struct SavedSearch: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var query: String
    var filters: SearchFilters
    var icon: String
    var isSmartSearch: Bool
    var folderPath: String
    var sortOrder: Int
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case query
        case filters
        case icon
        case isSmartSearch = "is_smart_search"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
    }

    init(
        id: String = UUID().uuidString,
        name: String,
        query: String = "",
        filters: SearchFilters = SearchFilters(),
        icon: String = "magnifyingglass",
        isSmartSearch: Bool = false,
        folderPath: String = "/",
        sortOrder: Int = 0,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.query = query
        self.filters = filters
        self.icon = icon
        self.isSmartSearch = isSmartSearch
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.createdAt = createdAt
    }
}

struct SearchFilters: Codable, Hashable {
    var docTypes: [DocType]?
    var fileTypes: [FileType]?
    var statuses: [Status]?
    var dateRange: DateRange?
    var hasContent: Bool?

    init(
        docTypes: [DocType]? = nil,
        fileTypes: [FileType]? = nil,
        statuses: [Status]? = nil,
        dateRange: DateRange? = nil,
        hasContent: Bool? = nil
    ) {
        self.docTypes = docTypes
        self.fileTypes = fileTypes
        self.statuses = statuses
        self.dateRange = dateRange
        self.hasContent = hasContent
    }
}

struct DateRange: Codable, Hashable {
    var start: Date?
    var end: Date?
}

// MARK: - Workflow
// Note: Full Workflow, WorkflowNode, WorkflowEdge models are defined in WorkflowService.swift
// This is a lightweight reference for sidebar display only

struct WorkflowSidebarItem: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var description: String?
    var nodeCount: Int
    var edgeCount: Int
    var isEnabled: Bool
    var folderPath: String
    var sortOrder: Int
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case nodeCount = "node_count"
        case edgeCount = "edge_count"
        case isEnabled = "is_enabled"
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(
        id: String = UUID().uuidString,
        name: String,
        description: String? = nil,
        nodeCount: Int = 0,
        edgeCount: Int = 0,
        isEnabled: Bool = true,
        folderPath: String = "/",
        sortOrder: Int = 0,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.nodeCount = nodeCount
        self.edgeCount = edgeCount
        self.isEnabled = isEnabled
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

// MARK: - App View Mode

/// Which main view is active based on sidebar selection
enum AppViewMode: Equatable {
    case library(Document?)           // Library browsing - selected collection/folder
    case search(SavedSearch?)         // Search view - selected saved search or new search
    case chat(Conversation?)          // Chat view - RAG conversation with documents
    case workflow(WorkflowSidebarItem?)  // Workflow editor - selected workflow

    var category: ItemCategory {
        switch self {
        case .library: return .folder
        case .search: return .search
        case .chat: return .chat
        case .workflow: return .workflow
        }
    }
}
