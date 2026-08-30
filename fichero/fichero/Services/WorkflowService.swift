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

    /// Port data-type conversion table SERVED BY THE ENGINE (#4477):
    /// output type → input types it may connect to, beyond same-type/"any".
    /// The canvas derives edge legality from this; it must never keep its own
    /// copy — a hand-written Swift table drifted to six conversions the
    /// engine rejects, so edges drew fine, saved fine, and died at run time.
    /// Empty until tools load; `canConnect` is strict (same-type/"any" only)
    /// in that window, which matches the engine minus its one conversion.
    private(set) var portConversions: [String: Set<String>] = [:]

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
            // The engine's conversion table rides on the same response (#4477).
            if let served = generatedTools.conversions?.additionalProperties {
                portConversions = served.mapValues(Set.init)
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
        case .ok(let okResponse):
            logger.info("createWorkflow: success")
            return try convertToWorkflowResponse(okResponse.body.json)
        case .unprocessableContent(let error):
            logger.error("createWorkflow: unprocessableContent - \(String(describing: error))")
            throw WorkflowServiceError.validationError("Invalid workflow data")
        default:
            logger.error("createWorkflow: unexpected response type - \(String(describing: response))")
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Presentation metadata for workflow folders — the order verbs appear in
    /// and the glyph each carries, as the ENGINE describes them.
    ///
    /// Read rather than hard-coded (2026-08-28): the bar's route order was a
    /// literal list in Swift because preset `sort_order` is 0 for every
    /// shipped preset. Serving it makes the order editable without a client
    /// build, and makes a user's own folder describable.
    func listWorkflowFolders() async throws -> [WorkflowFolderInfo] {
        let response = try await client.api.listWorkflowFoldersApiWorkflowsFoldersGet(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map {
                WorkflowFolderInfo(
                    path: $0.path,
                    displayName: $0.displayName,
                    sortOrder: $0.sortOrder,
                    icon: $0.icon
                )
            }
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// Realise a single TOOL as a one-step workflow so the engine can run it.
    ///
    /// The engine executes stored workflows only, so "run a tool" has to become
    /// one. Rather than a hidden special case, this creates a real workflow in
    /// a `/Tools` folder: reusable on later runs, openable in the node editor,
    /// and editable like any other — which is what makes the third level of the
    /// taxonomy (tools, workflows, chains) honest rather than a facade.
    ///
    /// Returns the new workflow's id.
    func createToolWorkflow(toolName: String, displayName: String) async throws -> String {
        guard let tool = getToolInfo(named: toolName) else {
            throw WorkflowServiceError.validationError("Unknown tool: \(toolName)")
        }
        let filesTool = getToolInfo(named: "files")
        var nodes: [WorkflowNode] = []
        if let filesTool {
            nodes.append(WorkflowNode(from: filesTool, positionX: 80, positionY: 200))
        }
        let toolNode = WorkflowNode(from: tool, positionX: 320, positionY: 200)
        nodes.append(toolNode)

        // Wire the source into the tool on matching port names, the same
        // pairing the shipped presets use (files -> files, documents ->
        // documents). Without edges the tool receives nothing and the run
        // completes green over zero documents.
        var edges: [WorkflowEdge] = []
        if let source = nodes.first, source.id != toolNode.id {
            for port in ["files", "documents"] where
                source.outputPorts.contains(where: { $0.id == port })
                && toolNode.inputPorts.contains(where: { $0.id == port }) {
                edges.append(WorkflowEdge(
                    sourceNodeId: source.id,
                    targetNodeId: toolNode.id,
                    sourcePortId: port,
                    targetPortId: port
                ))
            }
        }

        let definition = WorkflowDefinition(
            name: displayName,
            description: tool.description,
            nodes: nodes,
            edges: edges,
            folderPath: "/Tools"
        )
        return try await createWorkflow(definition).id
    }

    /// A run's cost CEILING for the given file count, priced by the engine's
    /// live model registry.
    ///
    /// A ceiling, never a point estimate (2026-08-28): the model is known, the
    /// item count is known and max_tokens is an explicit bound, so an upper
    /// limit is defensible where "about \$0.30" would be guesswork. Takes the
    /// provider/model override so a chain step priced with Opus is not quoted
    /// at the workflow's default.
    func estimateCost(
        workflowId: String,
        fileCount: Int,
        provider: String?,
        model: String?
    ) async throws -> Double? {
        let response = try await client.api
            .estimateWorkflowCostApiWorkflowsWorkflowIdEstimateCostPost(.init(
                path: .init(workflowId: workflowId),
                body: .json(.init(
                    fileCount: fileCount,
                    provider: provider,
                    model: model
                ))
            ))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            // UNPRICED is not free. The engine used to return 0.0 for a model
            // it could not price, and the bar showed "≤ US$0.00" for a
            // five-image run (Daniel, 2026-08-28). nil travels as "no figure".
            guard body.pricingAvailable == true else { return nil }
            return body.estimatedCostUsd
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }

    /// List all saved workflows. Pass `folderPath` to filter; omit for all.
    ///
    /// `summary` omits every workflow's node and edge graph, leaving
    /// `node_count` in their place — 263 KB becomes ~20 KB for 50 workflows,
    /// which is the difference between a sidebar folder opening instantly and
    /// visibly spinning. Callers that need a graph fetch it by id. Defaults
    /// to the full payload so no existing caller changes behaviour.
    func listWorkflows(
        folderPath: String? = nil,
        summary: Bool = false
    ) async throws -> [WorkflowResponse] {
        let libraryPath = client.currentLibraryPath ?? ""
        logger.info("listWorkflows called with libraryPath: \(libraryPath)")
        let response = try await client.api.listWorkflowsApiWorkflowsGet(.init(
            query: .init(folderPath: folderPath, summary: summary),
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
        case .undocumented(statusCode: 403, _):
            // Locked system preset: PUT is refused by design (#4514).
            throw WorkflowServiceError.readOnlyWorkflow
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
        case .undocumented(statusCode: 403, _):
            // Locked system preset: DELETE is refused by design (#4514).
            throw WorkflowServiceError.readOnlyWorkflow
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
        case .undocumented(statusCode: 403, _):
            // Locked system preset: rename is refused by design (#4514).
            throw WorkflowServiceError.readOnlyWorkflow
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
        case .undocumented(statusCode: 403, _):
            // Locked system preset: PATCH is refused by design (#4514).
            throw WorkflowServiceError.readOnlyWorkflow
        default:
            throw WorkflowServiceError.unexpectedResponse
        }
    }
}

// MARK: - Folders, import/export & presets (same-file extension:
// the class body budget; `client` stays private to this file)

extension WorkflowService {
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
        case .ok(let okResponse):
            return convertToWorkflowResponse(try okResponse.body.json)
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
