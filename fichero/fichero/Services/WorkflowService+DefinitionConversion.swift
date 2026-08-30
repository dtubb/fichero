import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowService")

// MARK: - Workflow Definition Conversion

extension WorkflowService {
    func convertToWorkflowDefinition(
        _ response: Components.Schemas.WorkflowResponse
    ) -> WorkflowDefinition {
        // Convert typed NodeDef to WorkflowNode
        let nodes: [WorkflowNode] = response.nodes.map { node in
            convertNodeDefToWorkflowNode(node)
        }

        // Convert typed EdgeDef to WorkflowEdge
        let edges: [WorkflowEdge] = response.edges.map { edge in
            convertEdgeDefToWorkflowEdge(edge)
        }

        return WorkflowDefinition(
            id: response.id,
            name: response.name,
            description: response.description,
            provider: response.provider,
            model: response.model,
            nodes: nodes,
            edges: edges,
            folderPath: response.folderPath,
            sortOrder: response.sortOrder
        )
    }

    func convertNodeDefToWorkflowNode(_ node: Components.Schemas.NodeDefOutput) -> WorkflowNode {
        // Convert input ports
        let inputPorts: [PortInfo] = (node.inputPorts ?? []).map { port in
            PortInfo(
                id: port.id,
                name: port.name,
                portType: port.portType == .input ? "input" : "output",
                dataType: port.dataType?.rawValue ?? "any",
                required: port.required ?? true,
                description: port.description ?? "",
                defaultValue: convertPortDefaultValue(port._default)
            )
        }

        // Convert output ports
        let outputPorts: [PortInfo] = (node.outputPorts ?? []).map { port in
            PortInfo(
                id: port.id,
                name: port.name,
                portType: port.portType == .input ? "input" : "output",
                dataType: port.dataType?.rawValue ?? "any",
                required: port.required ?? true,
                description: port.description ?? "",
                defaultValue: convertPortDefaultValue(port._default)
            )
        }

        // Convert input mappings
        let inputMappings: [InputMapping] = (node.inputMappings ?? []).map { mapping in
            InputMapping(
                portId: mapping.portId,
                sourcePath: mapping.sourcePath,
                transform: mapping.transform
            )
        }

        // Convert inputs dict
        var inputs: [String: AnyCodableValue]?
        if let inputsPayload = node.inputs {
            inputs = convertObjectContainerToAnyCodableValueDict(inputsPayload.additionalProperties)
        }

        // Convert config dict
        var config: [String: AnyCodableValue]?
        if let configPayload = node.config {
            config = convertObjectContainerToAnyCodableValueDict(configPayload.additionalProperties)
        }

        // Convert output schema
        var outputSchema: OutputSchema?
        if let schemaPayload = node.outputSchema {
            let jsonSchema = convertObjectContainerToAnyCodableValueDict(schemaPayload.schema.additionalProperties)
            outputSchema = OutputSchema(jsonSchema: jsonSchema, description: schemaPayload.description ?? "")
        }

        return WorkflowNode(
            id: node.id ?? UUID().uuidString,
            tool: node.tool,
            label: node.label,
            description: node.description,
            positionX: node.positionX ?? 0,
            positionY: node.positionY ?? 0,
            enabled: node.enabled ?? true,
            inputPorts: inputPorts,
            outputPorts: outputPorts,
            inputMappings: inputMappings,
            inputs: inputs,
            config: config,
            outputSchema: outputSchema,
            providerName: node.providerName,
            modelName: node.modelName,
            usesLLM: node.usesLlm ?? false
        )
    }

    func convertEdgeDefToWorkflowEdge(_ edge: Components.Schemas.EdgeDef) -> WorkflowEdge {
        WorkflowEdge(
            id: edge.id ?? UUID().uuidString,
            sourceNodeId: edge.source,
            targetNodeId: edge.target ?? "",
            sourcePortId: edge.sourcePort ?? "output",
            targetPortId: edge.targetPort ?? "input",
            condition: edge.condition,
            label: edge.label,
            animated: edge.animated ?? false,
            routeKey: edge.routeKey,
            routeMap: edge.routeMap?.additionalProperties
        )
    }
}

// MARK: - Generated Type Conversion

extension WorkflowService {
    func convertToGeneratedWorkflowDef(
        _ workflow: WorkflowDefinition
    ) throws -> Components.Schemas.WorkflowDef {
        let nodes = workflow.nodes.map { node in
            createNodeDef(from: node)
        }

        let edges = workflow.edges.map { edge in
            createEdgeDef(from: edge)
        }

        return Components.Schemas.WorkflowDef(
            id: workflow.id,
            name: workflow.name,
            description: workflow.description,
            nodes: nodes,
            edges: edges,
            provider: workflow.provider,
            model: workflow.model
        )
    }

    func createNodeDef(from node: WorkflowNode) -> Components.Schemas.NodeDefInput {
        let inputPorts = node.inputPorts.map { createPortDef(from: $0) }
        let outputPorts = node.outputPorts.map { createPortDef(from: $0) }

        // Convert input mappings
        let inputMappings: [Components.Schemas.InputMapping]? = node.inputMappings.isEmpty ? nil :
            node.inputMappings.map { mapping in
                Components.Schemas.InputMapping(
                    portId: mapping.portId,
                    sourcePath: mapping.sourcePath,
                    transform: mapping.transform
                )
            }

        // Convert inputs to OpenAPIObjectContainer
        var inputsPayload: Components.Schemas.NodeDefInput.InputsPayload?
        if let inputs = node.inputs, !inputs.isEmpty {
            do {
                let inputsDict = convertAnyCodableValueToDict(inputs)
                let container = try OpenAPIObjectContainer(unvalidatedValue: inputsDict)
                inputsPayload = Components.Schemas.NodeDefInput.InputsPayload(additionalProperties: container)
            } catch {
                logger.warning("Failed to convert node inputs: \(error)")
            }
        }

        // Convert config to OpenAPIObjectContainer
        var configPayload: Components.Schemas.NodeDefInput.ConfigPayload?
        if let config = node.config, !config.isEmpty {
            do {
                let configDict = convertAnyCodableValueToDict(config)
                let container = try OpenAPIObjectContainer(unvalidatedValue: configDict)
                configPayload = Components.Schemas.NodeDefInput.ConfigPayload(additionalProperties: container)
            } catch {
                logger.warning("Failed to convert node config: \(error)")
            }
        }

        // Convert output schema
        var outputSchemaPayload: Components.Schemas.OutputSchema?
        if let outputSchema = node.outputSchema {
            do {
                let schemaDict = convertAnyCodableValueToDict(outputSchema.jsonSchema)
                let container = try OpenAPIObjectContainer(unvalidatedValue: schemaDict)
                outputSchemaPayload = Components.Schemas.OutputSchema(
                    schema: .init(additionalProperties: container),
                    description: outputSchema.description
                )
            } catch {
                logger.warning("Failed to convert output schema: \(error)")
            }
        }

        return Components.Schemas.NodeDefInput(
            id: node.id,
            tool: node.tool,
            inputPorts: inputPorts,
            outputPorts: outputPorts,
            inputMappings: inputMappings,
            inputs: inputsPayload,
            config: configPayload,
            outputSchema: outputSchemaPayload,
            positionX: node.positionX,
            positionY: node.positionY,
            label: node.label,
            description: node.description,
            enabled: node.enabled,
            providerName: node.providerName,
            modelName: node.modelName,
            usesLlm: node.usesLLM
        )
    }

    /// Convert AnyCodableValue dictionary to standard dictionary for OpenAPIObjectContainer
    func convertAnyCodableValueToDict(_ dict: [String: AnyCodableValue]) -> [String: any Sendable] {
        var result: [String: any Sendable] = [:]
        for (key, value) in dict {
            switch value {
            case .string(let str): result[key] = str
            case .int(let num): result[key] = num
            case .double(let num): result[key] = num
            case .bool(let bool): result[key] = bool
            case .array(let arr): result[key] = arr.map { convertAnyCodableValueToAny($0) }
            case .dictionary(let nested): result[key] = convertAnyCodableValueToDict(nested)
            case .null: result[key] = NSNull()
            }
        }
        return result
    }

    func convertAnyCodableValueToAny(_ value: AnyCodableValue) -> any Sendable {
        switch value {
        case .string(let str): return str
        case .int(let num): return num
        case .double(let num): return num
        case .bool(let bool): return bool
        case .array(let arr): return arr.map { convertAnyCodableValueToAny($0) }
        case .dictionary(let dict): return convertAnyCodableValueToDict(dict)
        case .null: return NSNull()
        }
    }

    private func createEdgeDef(from edge: WorkflowEdge) -> Components.Schemas.EdgeDef {
        Components.Schemas.EdgeDef(
            id: edge.id,
            source: edge.sourceNodeId,
            target: edge.targetNodeId,
            sourcePort: edge.sourcePortId,
            targetPort: edge.targetPortId,
            condition: edge.condition,
            animated: edge.animated,
            label: edge.label
        )
    }

    private func createPortDef(from port: PortInfo) -> Components.Schemas.PortDef {
        let portType: Components.Schemas.PortDef.PortTypePayload = port.portType == "input" ? .input : .output

        // Convert default value if present
        var defaultPayload: OpenAPIRuntime.OpenAPIValueContainer?
        if let defaultValue = port.defaultValue {
            let anyValue = convertAnyCodableValueToAny(defaultValue)
            defaultPayload = try? OpenAPIRuntime.OpenAPIValueContainer(unvalidatedValue: anyValue)
        }

        return Components.Schemas.PortDef(
            id: port.id,
            name: port.name,
            portType: portType,
            dataType: Components.Schemas.DataType(rawValue: port.dataType),
            required: port.required,
            description: port.description,
            _default: defaultPayload
        )
    }
}

// MARK: - Container Helpers

extension WorkflowService {
    func convertObjectContainerToDict(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: any Sendable] {
        return container.value as [String: any Sendable]
    }

    func convertObjectContainerToAnyCodableDict(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: AnyCodable] {
        let dict = convertObjectContainerToDict(container)
        return dict.mapValues { AnyCodable($0) }
    }

    func convertObjectContainerToAnyCodable(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: AnyCodable] {
        convertObjectContainerToAnyCodableDict(container)
    }

    /// Convert Any value to AnyCodableValue (used for port default values)
    func convertAnyToAnyCodableValue(_ value: any Sendable) -> AnyCodableValue {
        switch value {
        case let str as String:
            return .string(str)
        case let num as Int:
            return .int(num)
        case let num as Double:
            return .double(num)
        case let bool as Bool:
            return .bool(bool)
        case let arr as [any Sendable]:
            return .array(arr.map { convertAnyToAnyCodableValue($0) })
        case let dict as [String: any Sendable]:
            var result: [String: AnyCodableValue] = [:]
            for (key, val) in dict {
                result[key] = convertAnyToAnyCodableValue(val)
            }
            return .dictionary(result)
        case is NSNull:
            return .null
        default:
            return .string(String(describing: value))
        }
    }
}

// MARK: - Errors

enum WorkflowServiceError: LocalizedError, Equatable {
    case unexpectedResponse
    case notFound(String)
    case validationError(String)
    /// The server refused a write to a locked system preset (HTTP 403,
    /// `_reject_if_read_only`, #4514). Typed so every save/rename/delete
    /// surface says what happened and what to do — never "Unexpected
    /// response from server".
    case readOnlyWorkflow

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .notFound(let message):
            return message
        case .validationError(let message):
            return "Validation error: \(message)"
        case .readOnlyWorkflow:
            return "This is a built-in workflow and can't be edited — duplicate it to customize."
        }
    }
}
