import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowService")

// Split from WorkflowService.swift (2026-08-30, file_length): the pure
// schema<->model mappers. No engine access — the service file keeps the
// private client; these are internal so it can still call them.
// MARK: - Type Conversions

extension WorkflowService {
    func convertToToolInfo(_ tool: Components.Schemas.ToolResponse) -> ToolInfo {
        let configDict: [String: AnyCodableValue]
        if let configSchema = tool.configSchema {
            configDict = convertObjectContainerToAnyCodableValueDict(configSchema.additionalProperties)
        } else {
            configDict = [:]
        }

        // Convert default_output_schema if present
        let defaultOutputSchema: [String: AnyCodableValue]?
        if let outputSchema = tool.defaultOutputSchema {
            defaultOutputSchema = convertObjectContainerToAnyCodableValueDict(outputSchema.additionalProperties)
        } else {
            defaultOutputSchema = nil
        }

        return ToolInfo(
            name: tool.name,
            displayName: tool.displayName,
            description: tool.description,
            category: tool.category,
            icon: tool.icon,
            color: tool.color,
            inputPorts: tool.inputPorts.map { convertPortResponseToPortInfo($0) },
            outputPorts: tool.outputPorts.map { convertPortResponseToPortInfo($0) },
            configSchema: configDict,
            defaultOutputSchema: defaultOutputSchema,
            defaultPrompt: tool.defaultPrompt,
            usesLLM: tool.usesLlm,
            supportsBatch: tool.supportsBatch,
            supportsStreaming: tool.supportsStreaming,
            supportsStructuredOutput: tool.supportsStructuredOutput,
            sortOrder: tool.sortOrder,
            parallelism: tool.parallelism
        )
    }

    func convertPortResponseToPortInfo(_ port: Components.Schemas.PortResponse) -> PortInfo {
        return PortInfo(
            id: port.id,
            name: port.name,
            portType: port.portType,
            dataType: port.dataType,
            required: port.required ?? true,
            description: port.description ?? "",
            defaultValue: convertPortDefaultValue(port._default)
        )
    }

    func convertPortDefaultValue(
        _ container: OpenAPIRuntime.OpenAPIValueContainer?
    ) -> AnyCodableValue? {
        guard let value = container?.value else { return nil }
        return convertAnyToAnyCodableValue(value)
    }

    func convertObjectContainerToAnyCodableValueDict(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: AnyCodableValue] {
        // AnyCodableValue doesn't have a simple init from Any,
        // so we use JSONEncoder/Decoder round-trip for proper conversion
        let dict = convertObjectContainerToDict(container)
        do {
            let data = try JSONSerialization.data(withJSONObject: dict)
            let decoded = try JSONDecoder().decode([String: AnyCodableValue].self, from: data)
            return decoded
        } catch {
            logger.warning("Failed to convert container to AnyCodableValue dict: \(error)")
            return [:]
        }
    }

    func convertToNodeResponse(
        _ node: Components.Schemas.NodeResponse
    ) throws -> NodeResponse {
        NodeResponse(
            id: node.id,
            tool: node.tool,
            label: node.label,
            description: node.description,
            inputPorts: node.inputPorts.map { convertPortResponseToPortInfo($0) },
            outputPorts: node.outputPorts.map { convertPortResponseToPortInfo($0) },
            positionX: node.positionX,
            positionY: node.positionY
        )
    }

    func convertToWorkflowResponse(
        _ workflow: Components.Schemas.WorkflowResponse
    ) -> WorkflowResponse {
        // Convert typed NodeDef to dict for legacy WorkflowResponse
        let nodeDicts: [[String: AnyCodable]] = workflow.nodes.map { node in
            var dict: [String: AnyCodable] = [
                "id": AnyCodable(node.id ?? ""),
                "tool": AnyCodable(node.tool),
                "position_x": AnyCodable(node.positionX ?? 0),
                "position_y": AnyCodable(node.positionY ?? 0),
                "enabled": AnyCodable(node.enabled ?? true),
                "uses_llm": AnyCodable(node.usesLlm ?? false)
            ]
            if let label = node.label { dict["label"] = AnyCodable(label) }
            if let desc = node.description { dict["description"] = AnyCodable(desc) }
            if let provider = node.providerName { dict["provider_name"] = AnyCodable(provider) }
            if let model = node.modelName { dict["model_name"] = AnyCodable(model) }
            return dict
        }
        let edgeDicts: [[String: AnyCodable]] = workflow.edges.map { edge in
            var dict: [String: AnyCodable] = [
                "id": AnyCodable(edge.id ?? ""),
                "source": AnyCodable(edge.source),
                "target": AnyCodable(edge.target ?? "")
            ]
            if let sourcePort = edge.sourcePort { dict["source_port"] = AnyCodable(sourcePort) }
            if let targetPort = edge.targetPort { dict["target_port"] = AnyCodable(targetPort) }
            if let cond = edge.condition { dict["condition"] = AnyCodable(cond) }
            if let anim = edge.animated { dict["animated"] = AnyCodable(anim) }
            return dict
        }
        // Extract is_system + untested via JSON round-trip since the generated
        // client can lag schema changes (both are derived backend response fields).
        let derived = Self.derivedFlags(from: workflow)
        return WorkflowResponse(
            id: workflow.id,
            name: workflow.name,
            description: workflow.description,
            provider: workflow.provider,
            model: workflow.model,
            nodes: nodeDicts,
            edges: edgeDicts,
            folderPath: workflow.folderPath,
            sortOrder: workflow.sortOrder,
            isSystem: derived.isSystem,
            isUntested: derived.isUntested,
            directRunnable: derived.directRunnable,
            acceptsModelOverride: derived.acceptsModelOverride,
            requiresVision: derived.requiresVision,
            nodeCount: derived.nodeCount,
            acceptedInputs: derived.acceptedInputs
        )
    }

    /// Backend-derived response flags, read via JSON round-trip rather than
    /// the generated properties because the generated client can lag a schema
    /// change. Every default here is the permissive one: an absent key means
    /// UNKNOWN, and unknown must never remove a control the user had.
    private struct DerivedFlags {
        var isSystem = false
        var isUntested = false
        var directRunnable = true
        var acceptsModelOverride = true
        // Not permissive-by-default in the same sense: `false` here means "do
        // not filter the model menu", which is the permissive outcome.
        var requiresVision = false
        // Counted server-side so a summary list can omit the graphs entirely
        // (#Phase 0). `nil` means the server did not say — the caller then
        // falls back to measuring whatever nodes it did receive, which is
        // exactly right for an older engine that still sends them.
        var nodeCount: Int?
        var acceptedInputs: [String]?
    }

    private static func derivedFlags(
        from workflow: Components.Schemas.WorkflowResponse
    ) -> DerivedFlags {
        guard let data = try? JSONEncoder().encode(workflow),
              let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return DerivedFlags()
        }
        return DerivedFlags(
            isSystem: (dict["is_system"] as? Bool) ?? false,
            isUntested: (dict["untested"] as? Bool) ?? false,
            directRunnable: (dict["direct_runnable"] as? Bool) ?? true,
            acceptsModelOverride: (dict["accepts_model_override"] as? Bool) ?? true,
            requiresVision: (dict["requires_vision"] as? Bool) ?? false,
            nodeCount: dict["node_count"] as? Int,
            acceptedInputs: dict["accepted_inputs"] as? [String]
        )
    }

}
