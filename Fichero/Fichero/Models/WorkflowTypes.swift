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
    
    enum CodingKeys: String, CodingKey {
        case id, name, description, provider, model, nodes, edges
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
    var providerName: String?
    var modelName: String?
    var usesLlm: Bool

    enum CodingKeys: String, CodingKey {
        case id, tool, label, description, enabled
        case positionX = "position_x"
        case positionY = "position_y"
        case inputPorts = "input_ports"
        case outputPorts = "output_ports"
        case inputMappings = "input_mappings"
        case providerName = "provider_name"
        case modelName = "model_name"
        case usesLlm = "uses_llm"
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
        providerName: String? = nil,
        modelName: String? = nil,
        usesLlm: Bool = false
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
        self.providerName = providerName
        self.modelName = modelName
        self.usesLlm = usesLlm
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
        providerName = try container.decodeIfPresent(String.self, forKey: .providerName)
        modelName = try container.decodeIfPresent(String.self, forKey: .modelName)
        usesLlm = try container.decodeIfPresent(Bool.self, forKey: .usesLlm) ?? false
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
        self.providerName = nil
        self.modelName = nil
        self.usesLlm = toolInfo.usesLlm
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
        case usesLlm = "uses_llm"
        case supportsBatch = "supports_batch"
        case supportsStreaming = "supports_streaming"
        case supportsStructuredOutput = "supports_structured_output"
        case sortOrder = "sort_order"
    }
}

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

struct DraggedEdge {
    let sourceNodeId: String
    let sourcePortId: String
    let startPoint: CGPoint
    var currentPoint: CGPoint
}