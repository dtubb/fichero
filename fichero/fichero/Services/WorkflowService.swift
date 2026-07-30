import Combine
import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowService")

/// WorkflowService using the generated OpenAPI client.
/// This replaces the manual APIClient with type-safe generated calls.
@MainActor
@Observable
class WorkflowService {
    private let client: FicheroClient

    /// Cached tools by name for quick lookup (populated when tools are loaded)
    private(set) var toolsByName: [String: ToolInfo] = [:]

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Get tool info by name from cache (returns nil if not loaded yet)
    func getToolInfo(named name: String) -> ToolInfo? {
        return toolsByName[name]
    }

    /// Fetch the dynamic prompt for a tool based on config
    func getToolPrompt(toolName: String, config: [String: any Sendable]) async throws -> String? {
        // Build the request body
        let configContainer = try OpenAPIObjectContainer(unvalidatedValue: config)

        let response = try await client.api.getToolPromptApiWorkflowsToolsToolNamePromptPost(.init(
            path: .init(toolName: toolName),
            headers: .init(),
            body: .json(.init(config: .init(additionalProperties: configContainer)))
        ))

        switch response {
        case .ok(let okResponse):
            let promptResponse = try okResponse.body.json
            return promptResponse.prompt
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    // MARK: - Tools

    /// List all available workflow tools with port definitions.
    func listTools() async throws -> [ToolInfo] {
        let response = try await client.api.listWorkflowToolsApiWorkflowsToolsGet(.init(
            headers: .init()
        ))
        switch response {
        case .ok(let okResponse):
            let generatedTools = try okResponse.body.json
            let tools = generatedTools.items.map { convertToToolInfo($0) }
            // Populate cache
            for tool in tools {
                toolsByName[tool.name] = tool
            }
            return tools
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Get details for a specific tool.
    func getTool(_ name: String) async throws -> ToolInfo {
        let response = try await client.api.getToolApiWorkflowsToolsToolNameGet(.init(
            path: .init(toolName: name),
            headers: .init()
        ))
        switch response {
        case .ok(let okResponse):
            return convertToToolInfo(try okResponse.body.json)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// List tools grouped by category.
    func listToolsGrouped() async throws -> ToolsGroupedResponse {
        let response = try await client.api.listToolsGroupedApiWorkflowsToolsGroupedGet(.init(
            headers: .init()
        ))
        switch response {
        case .ok(let okResponse):
            let grouped = try okResponse.body.json
            let categories = grouped.items.map { category in
                let tools = category.tools.map { convertToToolInfo($0) }
                // Populate cache
                for tool in tools {
                    toolsByName[tool.name] = tool
                }
                return CategoryTools(
                    category: category.category,
                    displayName: category.displayName,
                    tools: tools
                )
            }
            return ToolsGroupedResponse(categories: categories)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Create a new node from a tool.
    func createNode(
        toolName: String,
        positionX: Double = 0,
        positionY: Double = 0
    ) async throws -> NodeResponse {
        let response = try await client.api.createNodeApiWorkflowsToolsToolNameCreateNodePost(.init(
            path: .init(toolName: toolName),
            query: .init(positionX: positionX, positionY: positionY),
        ))
        switch response {
        case .ok(let okResponse):
            return try convertToNodeResponse(okResponse.body.json)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    // MARK: - Workflow CRUD

    /// Create a new workflow.
    func createWorkflow(_ workflow: WorkflowDefinition) async throws -> WorkflowResponse {
        let libraryPath = client.currentLibraryPath ?? ""
        logger.info("createWorkflow: libraryPath=\(libraryPath), name=\(workflow.name)")
        let request = try convertToGeneratedWorkflowDef(workflow)
        let response = try await client.api.createWorkflowApiWorkflowsPost(.init(
            body: .json(request)
        ))
        switch response {
        case .ok(let ok):
            logger.info("createWorkflow: success")
            return try convertToWorkflowResponse(ok.body.json)
        case .unprocessableContent(let error):
            logger.error("createWorkflow: unprocessableContent - \(String(describing: error))")
            throw WorkflowServiceError.validationError("Invalid workflow data")
        default:
            logger.error("createWorkflow: unexpected response type - \(String(describing: response))")
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// List all saved workflows. Pass `folderPath` to filter; omit for all.
    func listWorkflows(folderPath: String? = nil) async throws -> [WorkflowResponse] {
        let libraryPath = client.currentLibraryPath ?? ""
        logger.info("listWorkflows called with libraryPath: \(libraryPath)")
        let response = try await client.api.listWorkflowsApiWorkflowsGet(.init(
            query: .init(folderPath: folderPath),
        ))
        switch response {
        case .ok(let okResponse):
            let workflows = try okResponse.body.json
            logger.info("listWorkflows: got \(workflows.count) workflows")
            return workflows.items.map { convertToWorkflowResponse($0) }
        case .unprocessableContent(let error):
            logger.error("listWorkflows: unprocessableContent: \(String(describing: error))")
            throw WorkflowServiceError.validationError("Validation error")
        default:
            logger.error("listWorkflows: unexpected response type")
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Get a specific workflow by ID.
    func getWorkflow(_ id: String) async throws -> WorkflowDefinition {
        let response = try await client.api.getWorkflowApiWorkflowsWorkflowIdGet(.init(
            path: .init(workflowId: id),
        ))
        switch response {
        case .ok(let okResponse):
            let workflowResponse = try okResponse.body.json
            return convertToWorkflowDefinition(workflowResponse)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Update an existing workflow.
    func updateWorkflow(_ id: String, workflow: WorkflowDefinition) async throws -> WorkflowResponse {
        let request = try convertToGeneratedWorkflowDef(workflow)
        let response = try await client.api.updateWorkflowApiWorkflowsWorkflowIdPut(.init(
            path: .init(workflowId: id),
            body: .json(request)
        ))
        switch response {
        case .ok(let okResponse):
            return try convertToWorkflowResponse(okResponse.body.json)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Delete a workflow.
    func deleteWorkflow(_ id: String) async throws {
        let libraryPath = client.currentLibraryPath ?? ""
        logger.info("deleteWorkflow: id=\(id), libraryPath=\(libraryPath)")
        let response = try await client.api.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(
            path: .init(workflowId: id),
        ))
        switch response {
        case .ok:
            logger.info("deleteWorkflow: success")
            return
        default:
            logger.error("deleteWorkflow: unexpected response - \(String(describing: response))")
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Duplicate a workflow.
    func duplicateWorkflow(_ id: String) async throws -> WorkflowResponse {
        let response = try await client.api.duplicateWorkflowApiWorkflowsWorkflowIdDuplicatePost(.init(
            path: .init(workflowId: id),
        ))
        switch response {
        case .ok(let okResponse):
            return try convertToWorkflowResponse(okResponse.body.json)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Rename a workflow (uses backend PATCH for partial update).
    func renameWorkflow(_ id: String, newName: String) async throws -> WorkflowResponse {
        let libraryPath = client.currentLibraryPath ?? ""
        logger.info("renameWorkflow: id=\(id), newName=\(newName), libraryPath=\(libraryPath)")

        // Use typed fields on WorkflowPatchRequest (see 31fc4141).
        let body = Components.Schemas.WorkflowPatchRequest(name: newName)
        let response = try await client.api.patchWorkflowApiWorkflowsWorkflowIdPatch(.init(
            path: .init(workflowId: id),
            body: .json(body)
        ))
        switch response {
        case .ok(let okResponse):
            logger.info("renameWorkflow: success")
            return try convertToWorkflowResponse(okResponse.body.json)
        default:
            logger.error("renameWorkflow: unexpected response - \(String(describing: response))")
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Update a workflow properties (name, description, folder_path).
    func updateWorkflowProperties(
        _ id: String,
        name: String? = nil,
        description: String? = nil,
        folderPath: String? = nil,
        sortOrder: Int? = nil
    ) async throws -> WorkflowResponse {
        // Use typed fields on WorkflowPatchRequest (see 31fc4141).
        let body = Components.Schemas.WorkflowPatchRequest(
            name: name,
            description: description,
            folderPath: folderPath,
            sortOrder: sortOrder
        )
        let response = try await client.api.patchWorkflowApiWorkflowsWorkflowIdPatch(.init(
            path: .init(workflowId: id),
            body: .json(body)
        ))
        switch response {
        case .ok(let okResponse):
            return try convertToWorkflowResponse(okResponse.body.json)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Move workflow to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> WorkflowResponse {
        return try await updateWorkflowProperties(id, folderPath: folderPath)
    }

    /// Reorder workflows.
    func reorderWorkflows(_ workflowIds: [String], folderPath: String = "/") async throws {
        let response = try await client.api.reorderWorkflowsApiWorkflowsReorderPost(.init(
            query: .init(folderPath: folderPath),
            body: .json(workflowIds)
        ))
        switch response {
        case .ok:
            return
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Export a workflow as JSON data.
    func exportWorkflow(_ id: String) async throws -> [String: AnyCodable] {
        let response = try await client.api.exportWorkflowApiWorkflowsWorkflowIdExportGet(.init(
            path: .init(workflowId: id),
        ))
        switch response {
        case .ok(let okResponse):
            let exported = try okResponse.body.json
            // Re-encode the typed struct as JSON then decode into AnyCodable dict
            // so callers get the full workflow definition as a raw dictionary.
            let data = try JSONEncoder().encode(exported)
            return try JSONDecoder().decode([String: AnyCodable].self, from: data)
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Import a workflow from JSON data.
    func importWorkflow(
        name: String = "",
        description: String = "",
        workflowData: [String: AnyCodable]
    ) async throws -> WorkflowResponse {
        // Convert AnyCodable values to Sendable for OpenAPIObjectContainer.
        var sendableData: [String: any Sendable] = [:]
        sendableData.reserveCapacity(workflowData.count)
        for (key, value) in workflowData {
            sendableData[key] = value
        }
        let dataContainer = try OpenAPIObjectContainer(
            unvalidatedValue: sendableData
        )
        let bodyPayload = Operations.ImportWorkflowApiWorkflowsImportPost.Input.Body.JsonPayload(
            additionalProperties: dataContainer
        )

        let response = try await client.api.importWorkflowApiWorkflowsImportPost(.init(
            query: .init(name: name.isEmpty ? nil : name, description: description.isEmpty ? nil : description),
            body: .json(bodyPayload)
        ))

        switch response {
        case .ok(let ok):
            return convertToWorkflowResponse(try ok.body.json)
        case .unprocessableContent:
            throw WorkflowServiceError.validationError("Invalid workflow data")
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Fetch the workflow's LangGraph diagram as **mermaid source**.
    ///
    /// The `…/workflows/{id}/visualization` endpoint returns
    /// `WorkflowVisualizationResponse` JSON whose `mermaidCode` is mermaid
    /// diagram source (not image bytes) — despite the sibling `.png` route
    /// carrying the same JSON body. The view renders this live in a WKWebView
    /// (see `WorkflowMermaidView`), so this runs the generated op directly
    /// rather than the old raw-`URLSession` image fetch. Returns `nil` on any
    /// non-200 so a missing diagram degrades to the view's placeholder.
    func fetchDiagramMermaid(workflowId: String) async throws -> String? {
        let response = try await client.api
            .getWorkflowVisualizationApiWorkflowExecutionWorkflowsWorkflowIdVisualizationGet(.init(
                path: .init(workflowId: workflowId)
            ))
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.mermaidCode
        default:
            logger.warning("fetchDiagramMermaid: unexpected response for workflow \(workflowId)")
            return nil
        }
    }

    /// Reinstall default workflows from backend presets (Transcribe, Catalogue).
    /// Deletes existing presets and re-seeds so updated JSON reaches the library.
    func reinstallDefaults() async throws {
        // Library-scoped op (#1714): the header is required by the generated signature.
        let response = try await client.api.reinstallDefaultWorkflowsApiWorkflowsReinstallDefaultsPost(.init())
        switch response {
        case .ok:
            return
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }
}

// MARK: - Type Conversions

extension WorkflowService {
    private func convertToToolInfo(_ tool: Components.Schemas.ToolResponse) -> ToolInfo {
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
            sortOrder: tool.sortOrder
        )
    }

    private func convertPortResponseToPortInfo(_ port: Components.Schemas.PortResponse) -> PortInfo {
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

    private func convertPortDefaultValue(
        _ container: OpenAPIRuntime.OpenAPIValueContainer?
    ) -> AnyCodableValue? {
        guard let value = container?.value else { return nil }
        return convertAnyToAnyCodableValue(value)
    }

    private func convertObjectContainerToAnyCodableValueDict(
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

    private func convertToNodeResponse(
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

    private func convertToWorkflowResponse(
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
            if let sp = edge.sourcePort { dict["source_port"] = AnyCodable(sp) }
            if let tp = edge.targetPort { dict["target_port"] = AnyCodable(tp) }
            if let cond = edge.condition { dict["condition"] = AnyCodable(cond) }
            if let anim = edge.animated { dict["animated"] = AnyCodable(anim) }
            return dict
        }
        // Extract is_system + untested via JSON round-trip since the generated
        // client can lag schema changes (both are derived backend response fields).
        var isSystem = false
        var isUntested = false
        var directRunnable = true
        if let data = try? JSONEncoder().encode(workflow),
           let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            isSystem = (dict["is_system"] as? Bool) ?? false
            isUntested = (dict["untested"] as? Bool) ?? false
            directRunnable = (dict["direct_runnable"] as? Bool) ?? true
        }
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
            isSystem: isSystem,
            isUntested: isUntested,
            directRunnable: directRunnable
        )
    }

}

// MARK: - Workflow Definition Conversion

extension WorkflowService {
    private func convertToWorkflowDefinition(
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

    private func convertNodeDefToWorkflowNode(_ node: Components.Schemas.NodeDefOutput) -> WorkflowNode {
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

    private func convertEdgeDefToWorkflowEdge(_ edge: Components.Schemas.EdgeDef) -> WorkflowEdge {
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
    private func convertToGeneratedWorkflowDef(
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

    private func createNodeDef(from node: WorkflowNode) -> Components.Schemas.NodeDefInput {
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
    private func convertAnyCodableValueToDict(_ dict: [String: AnyCodableValue]) -> [String: any Sendable] {
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

    private func convertAnyCodableValueToAny(_ value: AnyCodableValue) -> any Sendable {
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
    private func convertObjectContainerToDict(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: any Sendable] {
        return container.value as [String: any Sendable]
    }

    private func convertObjectContainerToAnyCodableDict(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: AnyCodable] {
        let dict = convertObjectContainerToDict(container)
        return dict.mapValues { AnyCodable($0) }
    }

    private func convertObjectContainerToAnyCodable(
        _ container: OpenAPIRuntime.OpenAPIObjectContainer
    ) -> [String: AnyCodable] {
        convertObjectContainerToAnyCodableDict(container)
    }

    /// Convert Any value to AnyCodableValue (used for port default values)
    private func convertAnyToAnyCodableValue(_ value: any Sendable) -> AnyCodableValue {
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

enum WorkflowServiceError: LocalizedError {
    case unexpectedResponse
    case notFound(String)
    case validationError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .notFound(let message):
            return message
        case .validationError(let message):
            return "Validation error: \(message)"
        }
    }
}
