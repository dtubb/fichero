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
    /// False = the workflow pins its own provider/model, so the Run menu must
    /// not offer overrides that the engine would ignore. Absent = unknown, and
    /// unknown keeps the submenu (see `canOverrideModel`).
    var acceptsModelOverride: Bool?
    var createdAt: Date
    var updatedAt: Date
    /// Derived client-side at load (#4187), not wire data — deliberately NOT
    /// in CodingKeys. True when any node's tool uses an LLM in the "vision"
    /// category, mirroring the engine's preflight rule. Used only to FILTER
    /// the Run Workflow model submenu to vision-capable models; the engine
    /// remains the enforcement point, so `false` (e.g. after a failed tool
    /// registry fetch) fails OPEN to an unfiltered menu — never harden this
    /// into a client-side gate.
    var hasVisionNodes: Bool = false

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
        case acceptsModelOverride = "accepts_model_override"
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
        acceptsModelOverride: Bool = true,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        hasVisionNodes: Bool = false
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
        self.acceptsModelOverride = acceptsModelOverride
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.hasVisionNodes = hasVisionNodes
    }

    /// Engine parity (#4187): a workflow needs a vision-capable model iff any
    /// node's tool `usesLLM` and sits in the "vision" category — the same
    /// rule `validate_workflow_llm_preflight` enforces server-side. Unknown
    /// tools (registry miss) contribute `false`: the filter fails open and
    /// the engine still rejects a genuinely bad pick.
    static func requiresVisionModel(
        nodes: [[String: AnyCodable]],
        toolRegistry: [String: ToolInfo]
    ) -> Bool {
        nodes.contains { node in
            guard let tool = node["tool"]?.value as? String,
                  let info = toolRegistry[tool.lowercased()] else { return false }
            return info.usesLLM && info.category.lowercased() == "vision"
        }
    }

    /// Display name with the trust label appended (never stored in `name`).
    var displayName: String {
        isUntested ? "\(name) (Untested)" : name
    }

    var canRunDirectly: Bool { isDirectlyRunnable ?? true }

    /// Whether the Run menu should offer provider/model overrides. Unknown
    /// (nil) means yes: losing a control is worse than offering one the
    /// engine may ignore, and the engine remains the enforcement point.
    var canOverrideModel: Bool { acceptsModelOverride ?? true }
}
