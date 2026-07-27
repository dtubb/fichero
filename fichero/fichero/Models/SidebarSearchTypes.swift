import Foundation

// MARK: - Saved Search

struct SavedSearch: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var query: String
    var filters: SearchFilters
    var searchType: String
    var sortBy: String
    var sortDirection: String
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
        case searchType = "search_type"
        case sortBy = "sort_by"
        case sortDirection = "sort_direction"
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
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortDirection: String = "desc",
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
        self.searchType = searchType
        self.sortBy = sortBy
        self.sortDirection = sortDirection
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
    var isSystem: Bool
    // True = shipped preset not yet validated end-to-end; UI appends "(Untested)".
    var isUntested: Bool
    var isDirectlyRunnable: Bool?
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
        case isSystem = "is_system"
        case isUntested = "untested"
        case isDirectlyRunnable = "direct_runnable"
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
        isSystem: Bool = false,
        isUntested: Bool = false,
        isDirectlyRunnable: Bool = true,
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
        self.isSystem = isSystem
        self.isUntested = isUntested
        self.isDirectlyRunnable = isDirectlyRunnable
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    /// Display name with the trust label appended (never stored in `name`).
    var displayName: String {
        isUntested ? "\(name) (Untested)" : name
    }

    var canRunDirectly: Bool { isDirectlyRunnable ?? true }
}
