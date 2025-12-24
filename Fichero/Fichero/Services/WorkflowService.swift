import Foundation

/// Service for managing workflow tools and execution via the backend API.
actor WorkflowService {
    private let api = APIClient.shared

    // MARK: - Tools

    /// List all available workflow tools with port definitions.
    func listTools() async throws -> [ToolInfo] {
        try await api.get("/workflows/tools")
    }

    /// Get details for a specific tool.
    func getTool(_ name: String) async throws -> ToolInfo {
        try await api.get("/workflows/tools/\(name)")
    }

    /// List tools grouped by category.
    func listToolsGrouped() async throws -> ToolsGroupedResponse {
        try await api.get("/workflows/tools/grouped")
    }

    /// Create a new node from a tool.
    func createNode(toolName: String, positionX: Double = 0, positionY: Double = 0) async throws -> NodeResponse {
        try await api.post("/workflows/tools/\(toolName)/create-node?position_x=\(positionX)&position_y=\(positionY)")
    }

    // MARK: - Workflow Execution

    /// Run a workflow inline (without saving it).
    func runWorkflow(
        _ workflow: WorkflowDefinition,
        inputs: [String: Any] = [:],
        inputFiles: [String] = []
    ) async throws -> WorkflowRunResult {
        let request = RunWorkflowRequest(
            workflow: workflow,
            inputs: inputs,
            inputFiles: inputFiles
        )
        return try await api.post("/workflows/run", body: request)
    }
}

// MARK: - Port Definition

struct PortInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let portType: String  // "input" or "output"
    let dataType: String
    let required: Bool
    let description: String

    enum CodingKeys: String, CodingKey {
        case id, name, description, required
        case portType = "port_type"
        case dataType = "data_type"
    }

    /// Whether this is an input port
    var isInput: Bool { portType == "input" }

    /// Whether this is an output port
    var isOutput: Bool { portType == "output" }
}

// MARK: - Tool Definition

struct ToolInfo: Codable, Identifiable {
    let name: String
    let displayName: String
    let description: String
    let category: String
    let icon: String
    let color: String
    let inputPorts: [PortInfo]
    let outputPorts: [PortInfo]
    let configSchema: [String: AnyCodable]
    let defaultOutputSchema: [String: AnyCodable]?
    let usesLlm: Bool
    let supportsBatch: Bool
    let supportsStreaming: Bool
    let supportsStructuredOutput: Bool
    let sortOrder: Int

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name, description, category, icon, color
        case displayName = "display_name"
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case configSchema = "config_schema"
        case defaultOutputSchema = "default_output_schema"
        case usesLlm = "uses_llm"
        case supportsBatch = "supports_batch"
        case supportsStreaming = "supports_streaming"
        case supportsStructuredOutput = "supports_structured_output"
        case sortOrder = "sort_order"
    }

    /// SwiftUI Color for this tool
    var swiftUIColor: String { color }

    /// SF Symbol for this tool
    var systemImage: String { icon }
}

// MARK: - Tools Grouped Response

struct CategoryTools: Codable, Identifiable {
    let category: String
    let displayName: String
    let tools: [ToolInfo]

    var id: String { category }

    enum CodingKeys: String, CodingKey {
        case category, tools
        case displayName = "display_name"
    }
}

struct ToolsGroupedResponse: Codable {
    let categories: [CategoryTools]
}

// MARK: - Node Definition

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

struct InputMapping: Codable {
    let portId: String
    let sourcePath: String
    let transform: String?

    enum CodingKeys: String, CodingKey {
        case portId = "port_id"
        case sourcePath = "source_path"
        case transform
    }
}

struct NodeDefinition: Codable, Identifiable {
    let id: String
    var tool: String
    var inputPorts: [PortInfo]
    var outputPorts: [PortInfo]
    var inputMappings: [InputMapping]
    var config: [String: AnyCodable]
    var positionX: Double
    var positionY: Double
    var label: String?
    var description: String?
    var enabled: Bool

    enum CodingKeys: String, CodingKey {
        case id, tool, config, label, description, enabled
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case inputMappings = "input_mappings"
        case positionX = "position_x"
        case positionY = "position_y"
    }

    init(
        id: String = UUID().uuidString,
        tool: String,
        inputPorts: [PortInfo] = [],
        outputPorts: [PortInfo] = [],
        inputMappings: [InputMapping] = [],
        config: [String: AnyCodable] = [:],
        positionX: Double = 0,
        positionY: Double = 0,
        label: String? = nil,
        description: String? = nil,
        enabled: Bool = true
    ) {
        self.id = id
        self.tool = tool
        self.inputPorts = inputPorts
        self.outputPorts = outputPorts
        self.inputMappings = inputMappings
        self.config = config
        self.positionX = positionX
        self.positionY = positionY
        self.label = label
        self.description = description
        self.enabled = enabled
    }

    /// Create from a NodeResponse
    init(from response: NodeResponse) {
        self.id = response.id
        self.tool = response.tool
        self.inputPorts = response.inputPorts
        self.outputPorts = response.outputPorts
        self.inputMappings = []
        self.config = [:]
        self.positionX = response.positionX
        self.positionY = response.positionY
        self.label = response.label
        self.description = response.description
        self.enabled = true
    }
}

// MARK: - Edge Definition

struct EdgeDefinition: Codable, Identifiable {
    let id: String
    var source: String
    var target: String
    var sourcePort: String
    var targetPort: String
    var condition: String?
    var animated: Bool
    var label: String?

    enum CodingKeys: String, CodingKey {
        case id, source, target, condition, animated, label
        case sourcePort = "source_port"
        case targetPort = "target_port"
    }

    init(
        id: String = UUID().uuidString,
        source: String,
        target: String,
        sourcePort: String = "output",
        targetPort: String = "input",
        condition: String? = nil,
        animated: Bool = false,
        label: String? = nil
    ) {
        self.id = id
        self.source = source
        self.target = target
        self.sourcePort = sourcePort
        self.targetPort = targetPort
        self.condition = condition
        self.animated = animated
        self.label = label
    }
}

// MARK: - Workflow Definition

struct WorkflowDefinition: Codable, Identifiable {
    let id: String
    var name: String
    var description: String
    var nodes: [NodeDefinition]
    var edges: [EdgeDefinition]
    var provider: String
    var model: String
    var timeoutSeconds: Int
    var maxRetries: Int

    enum CodingKeys: String, CodingKey {
        case id, name, description, nodes, edges, provider, model
        case timeoutSeconds = "timeout_seconds"
        case maxRetries = "max_retries"
    }

    init(
        id: String = UUID().uuidString,
        name: String,
        description: String = "",
        nodes: [NodeDefinition] = [],
        edges: [EdgeDefinition] = [],
        provider: String = "openai",
        model: String = "gpt-4o",
        timeoutSeconds: Int = 300,
        maxRetries: Int = 3
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.nodes = nodes
        self.edges = edges
        self.provider = provider
        self.model = model
        self.timeoutSeconds = timeoutSeconds
        self.maxRetries = maxRetries
    }
}

// MARK: - Workflow Run

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

struct WorkflowRunResult: Codable {
    let taskId: String
    let workflowId: String
    let status: String
    let completedNodes: [String]
    let outputs: [String: AnyCodable]
    let outputFiles: [String]
    let error: String?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case workflowId = "workflow_id"
        case status
        case completedNodes = "completed_nodes"
        case outputs
        case outputFiles = "output_files"
        case error
    }

    /// True if workflow completed successfully
    var isSuccess: Bool {
        status == "completed" && error == nil
    }
}

// MARK: - SwiftUI Workflow Model (for UI state)

/// SwiftUI-friendly workflow model with observable state
struct Workflow: Identifiable {
    let id: String
    var name: String
    var description: String?
    var nodes: [WorkflowNode]
    var edges: [WorkflowEdge]
    var provider: String
    var model: String

    init(
        id: String = UUID().uuidString,
        name: String,
        description: String? = nil,
        nodes: [WorkflowNode] = [],
        edges: [WorkflowEdge] = [],
        provider: String = "openai",
        model: String = "gpt-4o"
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.nodes = nodes
        self.edges = edges
        self.provider = provider
        self.model = model
    }

    /// Convert to API WorkflowDefinition
    func toDefinition() -> WorkflowDefinition {
        WorkflowDefinition(
            id: id,
            name: name,
            description: description ?? "",
            nodes: nodes.map { $0.toDefinition() },
            edges: edges.map { $0.toDefinition() },
            provider: provider,
            model: model
        )
    }
}

/// A node in the workflow canvas
struct WorkflowNode: Identifiable {
    let id: String
    var tool: String
    var label: String
    var inputPorts: [PortInfo]
    var outputPorts: [PortInfo]
    var inputMappings: [InputMapping]
    var config: [String: Any]
    var positionX: Double
    var positionY: Double
    var enabled: Bool
    var usesLlm: Bool  // Whether this tool requires LLM provider/model selection

    // LLM settings (for LLM tools)
    var providerName: String?
    var modelName: String?

    init(
        id: String = UUID().uuidString,
        tool: String,
        label: String? = nil,
        inputPorts: [PortInfo] = [],
        outputPorts: [PortInfo] = [],
        inputMappings: [InputMapping] = [],
        config: [String: Any] = [:],
        positionX: Double = 0,
        positionY: Double = 0,
        enabled: Bool = true,
        usesLlm: Bool = false,
        providerName: String? = nil,
        modelName: String? = nil
    ) {
        self.id = id
        self.tool = tool
        self.label = label ?? tool.capitalized
        self.inputPorts = inputPorts
        self.outputPorts = outputPorts
        self.inputMappings = inputMappings
        self.config = config
        self.positionX = positionX
        self.positionY = positionY
        self.enabled = enabled
        self.usesLlm = usesLlm
        self.providerName = providerName
        self.modelName = modelName
    }

    /// Create from a ToolInfo
    init(from tool: ToolInfo, positionX: Double = 0, positionY: Double = 0) {
        self.id = "\(tool.name)_\(UUID().uuidString.prefix(8))"
        self.tool = tool.name
        self.label = tool.displayName
        self.inputPorts = tool.inputPorts
        self.outputPorts = tool.outputPorts
        self.inputMappings = []
        self.config = [:]
        self.positionX = positionX
        self.positionY = positionY
        self.enabled = true
        self.usesLlm = tool.usesLlm
        self.providerName = nil
        self.modelName = nil
    }

    func toDefinition() -> NodeDefinition {
        NodeDefinition(
            id: id,
            tool: tool,
            inputPorts: inputPorts,
            outputPorts: outputPorts,
            inputMappings: inputMappings,
            config: config.mapValues { AnyCodable($0) },
            positionX: positionX,
            positionY: positionY,
            label: label,
            enabled: enabled
        )
    }
}

/// An edge connecting two node ports
struct WorkflowEdge: Identifiable {
    let id: String
    var sourceNodeId: String
    var sourcePortId: String
    var targetNodeId: String
    var targetPortId: String
    var condition: String?
    var animated: Bool
    var label: String?

    init(
        id: String = UUID().uuidString,
        sourceNodeId: String,
        sourcePortId: String = "output",
        targetNodeId: String,
        targetPortId: String = "input",
        condition: String? = nil,
        animated: Bool = false,
        label: String? = nil
    ) {
        self.id = id
        self.sourceNodeId = sourceNodeId
        self.sourcePortId = sourcePortId
        self.targetNodeId = targetNodeId
        self.targetPortId = targetPortId
        self.condition = condition
        self.animated = animated
        self.label = label
    }

    func toDefinition() -> EdgeDefinition {
        EdgeDefinition(
            id: id,
            source: sourceNodeId,
            target: targetNodeId,
            sourcePort: sourcePortId,
            targetPort: targetPortId,
            condition: condition,
            animated: animated,
            label: label
        )
    }
}

