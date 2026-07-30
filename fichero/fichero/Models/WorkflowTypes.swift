import Foundation
import SwiftUI

// MARK: - Batch Input Source

/// Declares whether a workflow processes a named collection or the current library selection.
enum WorkflowInputSource: String, Codable, CaseIterable {
    case collection = "collection"
    case currentSelection = "current_selection"

    var displayName: String {
        switch self {
        case .collection: return "Entire Collection"
        case .currentSelection: return "Selected Documents"
        }
    }

    var icon: String {
        switch self {
        case .collection: return "folder"
        case .currentSelection: return "checkmark.circle"
        }
    }

    var helpText: String {
        switch self {
        case .collection: return "Run on every document in the current folder"
        case .currentSelection: return "Run only on documents you have selected in the library"
        }
    }
}

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
    let inputSource: WorkflowInputSource
    let isSystem: Bool
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
        case inputSource = "input_source"
        case isSystem = "is_system"
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
        inputSource: WorkflowInputSource = .collection,
        isSystem: Bool = false,
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
        self.inputSource = inputSource
        self.isSystem = isSystem
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
        inputSource = try container.decodeIfPresent(WorkflowInputSource.self, forKey: .inputSource) ?? .collection
        isSystem = try container.decodeIfPresent(Bool.self, forKey: .isSystem) ?? false
        timeoutSeconds = try container.decodeIfPresent(Int.self, forKey: .timeoutSeconds) ?? 300
        maxRetries = try container.decodeIfPresent(Int.self, forKey: .maxRetries) ?? 3
        version = try container.decodeIfPresent(String.self, forKey: .version) ?? "1.0"
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
    }
}

/// Workflow node model
struct WorkflowNode: Codable, Identifiable, Equatable {
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
    init(
        from toolInfo: ToolInfo,
        positionX: Double = 0,
        positionY: Double = 0,
        providerName: String? = nil,
        modelName: String? = nil
    ) {
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
        // Use config defaults from tool if available
        self.config = toolInfo.configDefaults.isEmpty ? nil : toolInfo.configDefaults
        self.outputSchema = toolInfo.defaultOutputSchema.map { OutputSchema(jsonSchema: $0) }
        self.providerName = providerName
        self.modelName = modelName
        self.usesLLM = toolInfo.usesLLM
    }
}

/// Workflow edge model
struct WorkflowEdge: Codable, Identifiable, Equatable {
    let id: String
    let sourceNodeId: String  // UI uses this
    let targetNodeId: String  // UI uses this
    let sourcePortId: String  // UI uses this
    let targetPortId: String  // UI uses this
    let condition: String?
    let label: String?
    let animated: Bool
    // Multi-way routing (EdgeDef.route_key / route_map from the engine).
    // route_key is a JSONPath expression evaluated against workflow state;
    // route_map maps resolved values to target node IDs.
    let routeKey: String?
    let routeMap: [String: String]?

    // Backend expects source/target/source_port/target_port, UI uses different names
    private enum CodingKeys: String, CodingKey {
        case id, source, target, condition, label, animated
        case sourcePort = "source_port"
        case targetPort = "target_port"
        case routeKey = "route_key"
        case routeMap = "route_map"
    }

    // Strict decoder (#4322): node ids and port ids are REQUIRED. The old
    // decoder silently defaulted missing ports to "output"/"input" (and
    // missing endpoints to ""), which made malformed edges render as
    // plausible-looking connections instead of surfacing the defect. The
    // engine's EdgeDef always serializes source/target/source_port/
    // target_port (pydantic defaults are included), so anything missing a
    // key is genuinely malformed and should fail loudly.
    // Note: `target` may legitimately be "" for route_map edges that fan to
    // multiple targets — the KEY must be present, the value may be empty.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        sourceNodeId = try container.decode(String.self, forKey: .source)
        targetNodeId = try container.decode(String.self, forKey: .target)
        sourcePortId = try container.decode(String.self, forKey: .sourcePort)
        targetPortId = try container.decode(String.self, forKey: .targetPort)
        condition = try container.decodeIfPresent(String.self, forKey: .condition)
        label = try container.decodeIfPresent(String.self, forKey: .label)
        animated = try container.decodeIfPresent(Bool.self, forKey: .animated) ?? false
        routeKey = try container.decodeIfPresent(String.self, forKey: .routeKey)
        routeMap = try container.decodeIfPresent([String: String].self, forKey: .routeMap)
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
        try container.encodeIfPresent(routeKey, forKey: .routeKey)
        try container.encodeIfPresent(routeMap, forKey: .routeMap)
    }

    init(
        id: String = UUID().uuidString,
        sourceNodeId: String,
        targetNodeId: String,
        sourcePortId: String = "output",
        targetPortId: String = "input",
        condition: String? = nil,
        label: String? = nil,
        animated: Bool = false,
        routeKey: String? = nil,
        routeMap: [String: String]? = nil
    ) {
        self.id = id
        self.sourceNodeId = sourceNodeId
        self.targetNodeId = targetNodeId
        self.sourcePortId = sourcePortId
        self.targetPortId = targetPortId
        self.condition = condition
        self.label = label
        self.animated = animated
        self.routeKey = routeKey
        self.routeMap = routeMap
    }
}

// WorkflowExecutionState is defined in WorkflowOutputLog.swift
