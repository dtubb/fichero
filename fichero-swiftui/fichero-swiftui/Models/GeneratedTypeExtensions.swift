import Foundation
import SwiftUI
import FicheroAPIClient
import OpenAPIRuntime

// MARK: - Generated Type Extensions
// These add convenience methods to generated types without creating conflicting type aliases.
// The manual types in WorkflowTypes.swift remain the primary types used by views.

// MARK: - NodeDefOutput Extensions

extension Components.Schemas.NodeDefOutput {
    /// Stable identifier for SwiftUI (handles optional id)
    public var stableId: String {
        self.id ?? "node-\(tool)-\(Int(positionX ?? 0))-\(Int(positionY ?? 0))"
    }
}

// MARK: - NodeDefInput Extensions

extension Components.Schemas.NodeDefInput {
    /// Stable identifier for SwiftUI
    public var stableId: String {
        self.id ?? "node-\(tool)-\(Int(positionX ?? 0))-\(Int(positionY ?? 0))"
    }
}

// MARK: - EdgeDef Extensions

extension Components.Schemas.EdgeDef {
    /// Stable identifier for SwiftUI (handles optional id)
    public var stableId: String {
        self.id ?? "edge-\(source)-\(target)"
    }

    /// Bridge: sourceNodeId property name (views use this)
    public var sourceNodeId: String { source }

    /// Bridge: targetNodeId property name (views use this)
    public var targetNodeId: String { target }

    /// Bridge: sourcePortId with default (views use this)
    public var sourcePortId: String { sourcePort ?? "output" }

    /// Bridge: targetPortId with default (views use this)
    public var targetPortId: String { targetPort ?? "input" }
}

// MARK: - PortDef Extensions

extension Components.Schemas.PortDef: @retroactive Identifiable {
    /// Whether this is an input port
    public var isInput: Bool { portType == .input }

    /// Whether this is an output port
    public var isOutput: Bool { portType == .output }
}

// MARK: - PortResponse Extensions

extension Components.Schemas.PortResponse: @retroactive Identifiable {
    /// Whether this is an input port
    public var isInput: Bool { portType == "input" }

    /// Whether this is an output port
    public var isOutput: Bool { portType == "output" }
}

// MARK: - ToolResponse Extensions

extension Components.Schemas.ToolResponse: @retroactive Identifiable {
    public var id: String { name }
}

// MARK: - CategoryToolsResponse Extensions

extension Components.Schemas.CategoryToolsResponse: @retroactive Identifiable {
    public var id: String { category }
}

// MARK: - InputMapping Extensions

extension Components.Schemas.InputMapping: @retroactive Identifiable {
    public var id: String { portId }
}

// MARK: - WorkflowResponse Extensions

extension Components.Schemas.WorkflowResponse: @retroactive Identifiable {
    /// Number of edges in the workflow
    public var edgeCount: Int { edges.count }
}

// MARK: - Other Identifiable Conformances

// NOTE: ScheduleResponse, TriggerResponse, ActionResponse, MCPServerResponse are not
// in the OpenAPI schema — corresponding routes exist in the backend but are not
// registered in main.py (schedules.py and triggers.py are orphaned).

extension Components.Schemas.ProviderResponse: @retroactive Identifiable {}

extension Components.Schemas.UserModelResponse: @retroactive Identifiable {}

extension Components.Schemas.ProviderCatalogResponse: @retroactive Identifiable {
    public var id: String { providerType }

    /// Alias for _type to match legacy naming
    public var providerType: String { _type }

    /// Convert color string to SwiftUI Color
    public var swiftUIColor: Color {
        switch color.lowercased() {
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "purple": return .purple
        case "red": return .red
        case "gray", "grey": return .gray
        case "pink": return .pink
        case "yellow": return .yellow
        case "cyan": return .cyan
        case "indigo": return .indigo
        case "mint": return .mint
        case "teal": return .teal
        default: return .accentColor
        }
    }
}

// MARK: - OpenAPIObjectContainer Helpers

extension OpenAPIRuntime.OpenAPIObjectContainer {
    /// Convert to dictionary for use with dynamic access
    var asDictionary: [String: Any] {
        var result: [String: Any] = [:]
        for (key, val) in self.value {
            if let unwrapped = val {
                result[key] = unwrapped
            }
        }
        return result
    }

    /// Get a string value by key
    func string(forKey key: String) -> String? {
        value[key] as? String
    }

    /// Get an integer value by key
    func int(forKey key: String) -> Int? {
        value[key] as? Int
    }

    /// Get a boolean value by key
    func bool(forKey key: String) -> Bool? {
        value[key] as? Bool
    }
}
