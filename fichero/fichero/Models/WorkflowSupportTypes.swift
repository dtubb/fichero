import Foundation
import SwiftUI

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
struct InputMapping: Codable, Identifiable, Equatable {
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
