import Foundation
import SwiftUI

// MARK: - Workflow Data Models

/// Workflow definition for API communication
struct WorkflowDefinition: Codable {
    let id: String
    let name: String
    let description: String
    let provider: String
    let model: String
    let nodes: [WorkflowNode]
    let edges: [WorkflowEdge]
    let folderPath: String
    let sortOrder: Int
    // Execution settings
    let timeoutSeconds: Int
    let maxRetries: Int
    // Metadata
    let version: String
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name, description, provider, model, nodes, edges, version
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
        case timeoutSeconds = "timeout_seconds"
        case maxRetries = "max_retries"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Convenience initializer with defaults for creating new workflows
    init(
        id: String = UUID().uuidString,
        name: String,
        description: String = "",
        provider: String = "",
        model: String = "",
        nodes: [WorkflowNode] = [],
        edges: [WorkflowEdge] = [],
        folderPath: String = "/",
        sortOrder: Int = 0,
        timeoutSeconds: Int = 300,
        maxRetries: Int = 3,
        version: String = "1.0",
        createdAt: String? = nil,
        updatedAt: String? = nil
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
        self.timeoutSeconds = timeoutSeconds
        self.maxRetries = maxRetries
        self.version = version
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
        provider = try container.decodeIfPresent(String.self, forKey: .provider) ?? ""
        model = try container.decodeIfPresent(String.self, forKey: .model) ?? ""
        nodes = try container.decodeIfPresent([WorkflowNode].self, forKey: .nodes) ?? []
        edges = try container.decodeIfPresent([WorkflowEdge].self, forKey: .edges) ?? []
        folderPath = try container.decodeIfPresent(String.self, forKey: .folderPath) ?? "/"
        sortOrder = try container.decodeIfPresent(Int.self, forKey: .sortOrder) ?? 0
        timeoutSeconds = try container.decodeIfPresent(Int.self, forKey: .timeoutSeconds) ?? 300
        maxRetries = try container.decodeIfPresent(Int.self, forKey: .maxRetries) ?? 3
        version = try container.decodeIfPresent(String.self, forKey: .version) ?? "1.0"
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

/// Workflow node model
struct WorkflowNode: Codable, Identifiable {
    let id: String
    let tool: String
    var label: String?
    var description: String?
    var positionX: Double
    var positionY: Double
    var enabled: Bool
    let inputPorts: [PortInfo]
    let outputPorts: [PortInfo]
    var inputMappings: [InputMapping]
    var inputs: [String: AnyCodableValue]?         // Input values (can be literal or path references)
    var config: [String: AnyCodableValue]?
    var outputSchema: OutputSchema?                 // Structured output schema for LLM nodes
    var providerName: String?
    var modelName: String?
    var usesLLM: Bool

    enum CodingKeys: String, CodingKey {
        case id, tool, label, description, enabled, config, inputs
        case positionX = "position_x"
        case positionY = "position_y"
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case inputMappings = "input_mappings"
        case outputSchema = "output_schema"
        case providerName = "provider_name"
        case modelName = "model_name"
        case usesLLM = "uses_llm"
    }

    init(
        id: String = UUID().uuidString,
        tool: String,
        label: String? = nil,
        description: String? = nil,
        positionX: Double = 0,
        positionY: Double = 0,
        enabled: Bool = true,
        inputPorts: [PortInfo] = [],
        outputPorts: [PortInfo] = [],
        inputMappings: [InputMapping] = [],
        inputs: [String: AnyCodableValue]? = nil,
        config: [String: AnyCodableValue]? = nil,
        outputSchema: OutputSchema? = nil,
        providerName: String? = nil,
        modelName: String? = nil,
        usesLLM: Bool = false
    ) {
        self.id = id
        self.tool = tool
        self.label = label
        self.description = description
        self.positionX = positionX
        self.positionY = positionY
        self.enabled = enabled
        self.inputPorts = inputPorts
        self.outputPorts = outputPorts
        self.inputMappings = inputMappings
        self.inputs = inputs
        self.config = config
        self.outputSchema = outputSchema
        self.providerName = providerName
        self.modelName = modelName
        self.usesLLM = usesLLM
    }

    // Custom decoder to handle defaults
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        tool = try container.decode(String.self, forKey: .tool)
        label = try container.decodeIfPresent(String.self, forKey: .label)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        positionX = try container.decodeIfPresent(Double.self, forKey: .positionX) ?? 0
        positionY = try container.decodeIfPresent(Double.self, forKey: .positionY) ?? 0
        enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        inputPorts = try container.decodeIfPresent([PortInfo].self, forKey: .inputPorts) ?? []
        outputPorts = try container.decodeIfPresent([PortInfo].self, forKey: .outputPorts) ?? []
        inputMappings = try container.decodeIfPresent([InputMapping].self, forKey: .inputMappings) ?? []
        inputs = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .inputs)
        config = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .config)
        outputSchema = try container.decodeIfPresent(OutputSchema.self, forKey: .outputSchema)
        providerName = try container.decodeIfPresent(String.self, forKey: .providerName)
        modelName = try container.decodeIfPresent(String.self, forKey: .modelName)
        usesLLM = try container.decodeIfPresent(Bool.self, forKey: .usesLLM) ?? false
    }

    /// Convenience initializer from ToolInfo
    init(from toolInfo: ToolInfo, positionX: Double = 0, positionY: Double = 0) {
        self.id = UUID().uuidString
        self.tool = toolInfo.name
        self.label = toolInfo.displayName
        self.description = toolInfo.description
        self.positionX = positionX
        self.positionY = positionY
        self.enabled = true
        self.inputPorts = toolInfo.inputPorts
        self.outputPorts = toolInfo.outputPorts
        self.inputMappings = []
        self.inputs = nil
        self.config = nil
        self.outputSchema = toolInfo.defaultOutputSchema.map { OutputSchema(jsonSchema: $0) }
        self.providerName = nil
        self.modelName = nil
        self.usesLLM = toolInfo.usesLLM
    }
}

/// Workflow edge model
struct WorkflowEdge: Codable, Identifiable {
    let id: String
    let sourceNodeId: String  // UI uses this
    let targetNodeId: String  // UI uses this
    let sourcePortId: String  // UI uses this
    let targetPortId: String  // UI uses this
    let condition: String?
    let label: String?
    let animated: Bool

    // Backend expects source/target/source_port/target_port, UI uses different names
    private enum CodingKeys: String, CodingKey {
        case id, source, target, condition, label, animated
        case sourcePort = "source_port"
        case targetPort = "target_port"
    }

    // Custom decoder to handle both sourceNodeId (UI) and source (backend)
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)

        // Try backend names first (source/target), then fallback to UI names if needed
        sourceNodeId = (try? container.decode(String.self, forKey: .source)) ?? ""
        targetNodeId = (try? container.decode(String.self, forKey: .target)) ?? ""

        sourcePortId = (try? container.decode(String.self, forKey: .sourcePort)) ?? "output"
        targetPortId = (try? container.decode(String.self, forKey: .targetPort)) ?? "input"
        condition = try? container.decodeIfPresent(String.self, forKey: .condition)
        label = try? container.decodeIfPresent(String.self, forKey: .label)
        animated = (try? container.decodeIfPresent(Bool.self, forKey: .animated)) ?? false
    }

    // Custom encoder to always write backend format (source/target)
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(sourceNodeId, forKey: .source)
        try container.encode(targetNodeId, forKey: .target)
        try container.encode(sourcePortId, forKey: .sourcePort)
        try container.encode(targetPortId, forKey: .targetPort)
        try container.encodeIfPresent(condition, forKey: .condition)
        try container.encodeIfPresent(label, forKey: .label)
        try container.encode(animated, forKey: .animated)
    }

    init(
        id: String = UUID().uuidString,
        sourceNodeId: String,
        targetNodeId: String,
        sourcePortId: String = "output",
        targetPortId: String = "input",
        condition: String? = nil,
        label: String? = nil,
        animated: Bool = false
    ) {
        self.id = id
        self.sourceNodeId = sourceNodeId
        self.targetNodeId = targetNodeId
        self.sourcePortId = sourcePortId
        self.targetPortId = targetPortId
        self.condition = condition
        self.label = label
        self.animated = animated
    }
}

// WorkflowExecutionState is defined in WorkflowOutputLog.swift

// MARK: - Output Schema

/// JSON Schema for structured output from LLM nodes.
/// When specified, the LLM will return data matching this schema exactly.
struct OutputSchema: Codable, Hashable {
    let jsonSchema: [String: AnyCodableValue]
    let description: String

    enum CodingKeys: String, CodingKey {
        case jsonSchema = "schema"  // Python uses "schema" as alias for "json_schema"
        case description
    }

    init(jsonSchema: [String: AnyCodableValue], description: String = "") {
        self.jsonSchema = jsonSchema
        self.description = description
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jsonSchema = try container.decodeIfPresent([String: AnyCodableValue].self, forKey: .jsonSchema) ?? [:]
        description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    }
}

// MARK: - Input Mapping

/// Maps a node input port to a data source
struct InputMapping: Codable, Identifiable {
    var id: String { portId }
    let portId: String
    var sourcePath: String
    var transform: String?

    enum CodingKeys: String, CodingKey {
        case portId = "port_id"
        case sourcePath = "source_path"
        case transform
    }

    init(portId: String, sourcePath: String, transform: String? = nil) {
        self.portId = portId
        self.sourcePath = sourcePath
        self.transform = transform
    }
}

// MARK: - Supporting Types

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

struct ToolInfo: Codable, Identifiable {
    let name: String
    let displayName: String
    let description: String
    let category: String
    let icon: String
    let color: String
    let inputPorts: [PortInfo]
    let outputPorts: [PortInfo]
    let configSchema: [String: AnyCodableValue]
    let defaultOutputSchema: [String: AnyCodableValue]?  // Default structured output schema
    let defaultPrompt: String?  // Default prompt for LLM tools (from backend)
    let usesLLM: Bool
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
        case defaultPrompt = "default_prompt"
        case usesLLM = "uses_llm"
        case supportsBatch = "supports_batch"
        case supportsStreaming = "supports_streaming"
        case supportsStructuredOutput = "supports_structured_output"
        case sortOrder = "sort_order"
    }

    /// Memberwise initializer for creating ToolInfo from code
    init(
        name: String,
        displayName: String,
        description: String,
        category: String,
        icon: String,
        color: String,
        inputPorts: [PortInfo],
        outputPorts: [PortInfo],
        configSchema: [String: AnyCodableValue] = [:],
        defaultOutputSchema: [String: AnyCodableValue]? = nil,
        defaultPrompt: String? = nil,
        usesLLM: Bool,
        supportsBatch: Bool,
        supportsStreaming: Bool,
        supportsStructuredOutput: Bool,
        sortOrder: Int
    ) {
        self.name = name
        self.displayName = displayName
        self.description = description
        self.category = category
        self.icon = icon
        self.color = color
        self.inputPorts = inputPorts
        self.outputPorts = outputPorts
        self.configSchema = configSchema
        self.defaultOutputSchema = defaultOutputSchema
        self.defaultPrompt = defaultPrompt
        self.usesLLM = usesLLM
        self.supportsBatch = supportsBatch
        self.supportsStreaming = supportsStreaming
        self.supportsStructuredOutput = supportsStructuredOutput
        self.sortOrder = sortOrder
    }
}

/// Codable wrapper for Any values in config schemas
enum AnyCodableValue: Codable, Hashable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case array([AnyCodableValue])
    case dictionary([String: AnyCodableValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            self = .string(string)
        } else if let int = try? container.decode(Int.self) {
            self = .int(int)
        } else if let double = try? container.decode(Double.self) {
            self = .double(double)
        } else if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
        } else if let array = try? container.decode([AnyCodableValue].self) {
            self = .array(array)
        } else if let dict = try? container.decode([String: AnyCodableValue].self) {
            self = .dictionary(dict)
        } else if container.decodeNil() {
            self = .null
        } else {
            throw DecodingError.typeMismatch(
                AnyCodableValue.self,
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Unsupported type")
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .dictionary(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

struct PortInfo: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let portType: String  // "input" or "output"
    let dataType: String
    let required: Bool
    let description: String
    let defaultValue: AnyCodableValue?  // Default value for optional inputs

    enum CodingKeys: String, CodingKey {
        case id, name, description, required
        case portType = "port_type"
        case dataType = "data_type"
        case defaultValue = "default"
    }

    init(
        id: String,
        name: String,
        portType: String,
        dataType: String,
        required: Bool = true,
        description: String = "",
        defaultValue: AnyCodableValue? = nil
    ) {
        self.id = id
        self.name = name
        self.portType = portType
        self.dataType = dataType
        self.required = required
        self.description = description
        self.defaultValue = defaultValue
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        portType = try container.decode(String.self, forKey: .portType)
        dataType = try container.decode(String.self, forKey: .dataType)
        required = try container.decodeIfPresent(Bool.self, forKey: .required) ?? true
        description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
        defaultValue = try container.decodeIfPresent(AnyCodableValue.self, forKey: .defaultValue)
    }

    /// Whether this is an input port
    var isInput: Bool { portType == "input" }

    /// Whether this is an output port
    var isOutput: Bool { portType == "output" }
}

struct DraggedEdge {
    let sourceNodeId: String
    let sourcePortId: String
    let startPoint: CGPoint
    var currentPoint: CGPoint
}

// MARK: - Agent Types

/// Agent types for workflow nodes and configuration
/// This is the canonical definition - use this throughout the app
enum AgentType: String, CaseIterable, Codable {
    case react = "react"
    case toolCalling = "tool_calling"
    case planAndExecute = "plan_execute"

    var displayName: String {
        switch self {
        case .react:
            return "ReAct"
        case .toolCalling:
            return "Tool Calling"
        case .planAndExecute:
            return "Plan & Execute"
        }
    }

    var icon: String {
        switch self {
        case .react:
            return "brain"
        case .toolCalling:
            return "wrench.and.screwdriver"
        case .planAndExecute:
            return "list.bullet.clipboard"
        }
    }

    var description: String {
        switch self {
        case .react:
            return "Reasoning + Acting loop: The agent thinks step-by-step and decides which tools to use."
        case .toolCalling:
            return "Direct tool invocation: The agent calls tools directly based on the input."
        case .planAndExecute:
            return "Creates a plan first, then executes steps sequentially."
        }
    }
}

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

    enum CodingKeys: String, CodingKey {
        case id, name, description, provider, model, nodes, edges
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
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
