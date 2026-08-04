import Foundation

// MARK: - Service Response Types

/// Response containing tools grouped by category
struct ToolsGroupedResponse: Codable {
    let categories: [CategoryTools]
}

/// Response for a created/fetched node
struct NodeResponse: Codable, Identifiable {
    let id: String
    let tool: String
    let label: String?
    let description: String?
    let inputPorts: [PortInfo]
    let outputPorts: [PortInfo]
    let positionX: Double
    let positionY: Double

    enum CodingKeys: String, CodingKey {
        case id, tool, label, description
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case positionX = "position_x"
        case positionY = "position_y"
    }
}

/// Request to run a workflow inline
struct RunWorkflowRequest: Encodable {
    let workflow: WorkflowDefinition
    let inputs: [String: AnyCodable]
    let inputFiles: [String]

    enum CodingKeys: String, CodingKey {
        case workflow, inputs
        case inputFiles = "input_files"
    }

    init(workflow: WorkflowDefinition, inputs: [String: Any], inputFiles: [String]) {
        self.workflow = workflow
        self.inputs = inputs.mapValues { AnyCodable($0) }
        self.inputFiles = inputFiles
    }
}

/// Workflow response from API (uses AnyCodable for nodes/edges)
struct WorkflowResponse: Codable {
    let id: String
    let name: String
    let description: String
    let provider: String
    let model: String
    let nodes: [[String: AnyCodable]]
    let edges: [[String: AnyCodable]]
    let folderPath: String
    let sortOrder: Int
    let isSystem: Bool
    // True = shipped preset not yet validated end-to-end; UI appends "(Untested)".
    var isUntested: Bool = false
    let directRunnable: Bool?
    /// False = this workflow pins its own provider/model, so a per-run
    /// override would be silently ignored. Optional + absent means unknown,
    /// which callers must read as `true`: a workflow whose capability we
    /// cannot determine keeps its override controls rather than losing them.
    let acceptsModelOverride: Bool?
    /// Server-computed answer to "does running this need a vision model?",
    /// from the same `workflow_requires_vision` rule the engine's preflight
    /// enforces — which descends into `sub_workflow` children (cycle-guarded).
    /// The client cannot compute this from its own node list, because a
    /// parent's vision requirement can live entirely in a child. Absent
    /// (old server) means `false`, which fails OPEN to an unfiltered menu.
    var requiresVision: Bool = false

    enum CodingKeys: String, CodingKey {
        case id, name, description, provider, model, nodes, edges
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case isSystem = "is_system"
        case isUntested = "untested"
        case directRunnable = "direct_runnable"
        case acceptsModelOverride = "accepts_model_override"
        case requiresVision = "requires_vision"
    }

    /// Hand-written because the synthesized decoder IGNORES the property
    /// defaults above: it calls `decode`, not `decodeIfPresent`, for every
    /// non-optional key, so an older engine's payload without
    /// `requires_vision` (or `untested`) failed to decode AT ALL — the exact
    /// opposite of the fail-open contract both fields document. The two
    /// derived flags fall back to their declared defaults when absent;
    /// everything else keeps synthesized strictness.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decode(String.self, forKey: .description)
        provider = try container.decode(String.self, forKey: .provider)
        model = try container.decode(String.self, forKey: .model)
        nodes = try container.decode([[String: AnyCodable]].self, forKey: .nodes)
        edges = try container.decode([[String: AnyCodable]].self, forKey: .edges)
        folderPath = try container.decode(String.self, forKey: .folderPath)
        sortOrder = try container.decode(Int.self, forKey: .sortOrder)
        isSystem = try container.decode(Bool.self, forKey: .isSystem)
        isUntested = try container.decodeIfPresent(Bool.self, forKey: .isUntested) ?? false
        directRunnable = try container.decodeIfPresent(Bool.self, forKey: .directRunnable)
        acceptsModelOverride = try container.decodeIfPresent(Bool.self, forKey: .acceptsModelOverride)
        requiresVision = try container.decodeIfPresent(Bool.self, forKey: .requiresVision) ?? false
    }

    /// The memberwise init the compiler stops synthesizing once `init(from:)`
    /// exists — `convertToWorkflowResponse` builds instances with it.
    init(
        id: String,
        name: String,
        description: String,
        provider: String,
        model: String,
        nodes: [[String: AnyCodable]],
        edges: [[String: AnyCodable]],
        folderPath: String,
        sortOrder: Int,
        isSystem: Bool,
        isUntested: Bool = false,
        directRunnable: Bool?,
        acceptsModelOverride: Bool?,
        requiresVision: Bool = false
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.provider = provider
        self.model = model
        self.nodes = nodes
        self.edges = edges
        self.folderPath = folderPath
        self.sortOrder = sortOrder
        self.isSystem = isSystem
        self.isUntested = isUntested
        self.directRunnable = directRunnable
        self.acceptsModelOverride = acceptsModelOverride
        self.requiresVision = requiresVision
    }
}

// MARK: - Workflow Execution State

/// Execution state for a single workflow node during runtime
enum NodeExecutionStatus: String, Codable {
    case idle = "idle"
    case running = "running"
    case parallelRunning = "parallel_running"
    case completed = "completed"
    case failed = "failed"
}

/// Tracks execution progress for a workflow node
struct NodeExecutionState: Identifiable {
    let nodeId: String
    var displayName: String?
    var status: NodeExecutionStatus = .idle
    var progress: Double = 0.0  // 0.0 to 1.0
    var fileIndex: Int = 0
    var fileTotal: Int = 0
    var successCount: Int = 0
    var errorCount: Int = 0
    var currentFile: String?
    var errorMessage: String?

    var id: String { nodeId }

    /// Whether this node is currently processing files in parallel
    var isParallelProcessing: Bool {
        status == .parallelRunning && fileTotal > 0
    }

    /// Progress text for display (e.g., "5/10")
    var progressText: String? {
        guard isParallelProcessing else { return nil }
        return "\(successCount + errorCount)/\(fileTotal)"
    }
}

/// Workflow execution SSE event from backend
struct WorkflowSSEEvent: Codable {
    let event: String
    let threadId: String
    let workflowId: String
    let data: [String: AnyCodableValue]
    let timestamp: String
    // Parallel execution fields
    let nodeId: String?
    let filePath: String?
    let fileIndex: Int?
    let fileTotal: Int?
    let progress: Double?

    enum CodingKeys: String, CodingKey {
        case event, data, timestamp
        case threadId = "thread_id"
        case workflowId = "workflow_id"
        case nodeId = "node_id"
        case filePath = "file_path"
        case fileIndex = "file_index"
        case fileTotal = "file_total"
        case progress
    }
}
