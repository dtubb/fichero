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
    /// The SERVER's answer to "does running this need a vision model?", read
    /// from `requires_vision` on the workflow response — never recomputed
    /// here. The client used to derive it from its own node list, which got
    /// the sub-workflow case wrong: a parent whose only vision node lives in
    /// a `sub_workflow` child looked text-only, so the Run menu offered
    /// text-only models the engine then rejected (#3804). The engine's
    /// `workflow_requires_vision` descends into children with a cycle guard.
    /// Used only to FILTER the Run Workflow model submenu; the engine remains
    /// the enforcement point, so `false` (old server, absent key) fails OPEN
    /// to an unfiltered menu — never harden this into a client-side gate.
    var requiresVision: Bool = false

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
        case requiresVision = "requires_vision"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Hand-written because the synthesized decoder ignores the `= false`
    /// default on `requiresVision`: it demands the key, so a pre-#3804 row
    /// (older engine, persisted sidebar cache) failed to decode entirely
    /// instead of failing OPEN to an unfiltered model menu as documented.
    /// Only `requiresVision` gets the tolerant read; every other field keeps
    /// synthesized strictness.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        nodeCount = try container.decode(Int.self, forKey: .nodeCount)
        edgeCount = try container.decode(Int.self, forKey: .edgeCount)
        isEnabled = try container.decode(Bool.self, forKey: .isEnabled)
        folderPath = try container.decode(String.self, forKey: .folderPath)
        sortOrder = try container.decode(Int.self, forKey: .sortOrder)
        isSystem = try container.decode(Bool.self, forKey: .isSystem)
        isUntested = try container.decode(Bool.self, forKey: .isUntested)
        isDirectlyRunnable = try container.decodeIfPresent(Bool.self, forKey: .isDirectlyRunnable)
        acceptsModelOverride = try container.decodeIfPresent(Bool.self, forKey: .acceptsModelOverride)
        requiresVision = try container.decodeIfPresent(Bool.self, forKey: .requiresVision) ?? false
        createdAt = try container.decode(Date.self, forKey: .createdAt)
        updatedAt = try container.decode(Date.self, forKey: .updatedAt)
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
        requiresVision: Bool = false
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
        self.requiresVision = requiresVision
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
