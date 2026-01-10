import Foundation
import Combine
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowService")

/// Service for managing workflow tools and execution via the backend API.
@MainActor
class WorkflowService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

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

    // MARK: - Workflow CRUD

    /// Create a new workflow.
    func createWorkflow(_ workflow: WorkflowDefinition) async throws -> WorkflowResponse {
        return try await api.post("/workflows", body: workflow)
    }

    /// List all saved workflows.
    func listWorkflows(folderPath: String = "/") async throws -> [WorkflowResponse] {
        return try await api.get("/workflows", query: ["folder_path": folderPath])
    }

    /// Get a specific workflow by ID.
    /// Nodes include embedded port definitions - no additional API calls needed.
    func getWorkflow(_ id: String) async throws -> WorkflowDefinition {
        let response: WorkflowResponse = try await api.get("/workflows/\(id)")

        // Convert the response nodes to WorkflowNode objects
        // Port definitions are embedded in node data - no need to fetch from tool registry
        var nodes: [WorkflowNode] = []
        for nodeDict in response.nodes {
            let nodeId = (nodeDict["id"]?.value as? String) ?? UUID().uuidString
            let tool = (nodeDict["tool"]?.value as? String) ?? ""
            let label = nodeDict["label"]?.value as? String
            let description = nodeDict["description"]?.value as? String
            let positionX = (nodeDict["position_x"]?.value as? Double) ?? 0.0
            let positionY = (nodeDict["position_y"]?.value as? Double) ?? 0.0
            let enabled = (nodeDict["enabled"]?.value as? Bool) ?? true

            // Extract port definitions from node data (already embedded when workflow was saved)
            let inputPorts = extractPorts(from: nodeDict, key: "input_ports")
            let outputPorts = extractPorts(from: nodeDict, key: "output_ports")

            let node = WorkflowNode(
                id: nodeId,
                tool: tool,
                label: label,
                description: description,
                positionX: positionX,
                positionY: positionY,
                enabled: enabled,
                inputPorts: inputPorts,
                outputPorts: outputPorts
            )
            nodes.append(node)
        }

        // Convert the response edges to WorkflowEdge objects
        var edges: [WorkflowEdge] = []
        for edgeDict in response.edges {
            let edgeId = (edgeDict["id"]?.value as? String) ?? UUID().uuidString
            let source = (edgeDict["source"]?.value as? String) ?? ""
            let target = (edgeDict["target"]?.value as? String) ?? ""
            let sourcePortId = (edgeDict["source_port"]?.value as? String) ?? "output"
            let targetPortId = (edgeDict["target_port"]?.value as? String) ?? "input"
            let condition = edgeDict["condition"]?.value as? String
            let label = edgeDict["label"]?.value as? String
            let animated = (edgeDict["animated"]?.value as? Bool) ?? false

            let edge = WorkflowEdge(
                id: edgeId,
                sourceNodeId: source,
                targetNodeId: target,
                sourcePortId: sourcePortId,
                targetPortId: targetPortId,
                condition: condition,
                label: label,
                animated: animated
            )
            edges.append(edge)
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

    /// Extract port definitions from node dictionary.
    private func extractPorts(from nodeDict: [String: AnyCodable], key: String) -> [PortInfo] {
        guard let portsValue = nodeDict[key]?.value,
              let portsArray = portsValue as? [[String: Any]] else {
            return []
        }

        return portsArray.compactMap { portDict -> PortInfo? in
            guard let id = portDict["id"] as? String,
                  let name = portDict["name"] as? String,
                  let portType = portDict["port_type"] as? String,
                  let dataType = portDict["data_type"] as? String else {
                return nil
            }

            return PortInfo(
                id: id,
                name: name,
                portType: portType,
                dataType: dataType,
                required: portDict["required"] as? Bool ?? true,
                description: portDict["description"] as? String ?? ""
            )
        }
    }

    /// Update an existing workflow.
    func updateWorkflow(_ id: String, workflow: WorkflowDefinition) async throws -> WorkflowResponse {
        return try await api.put("/workflows/\(id)", body: workflow)
    }

    /// Delete a workflow.
    func deleteWorkflow(_ id: String) async throws {
        _ = try await api.delete("/workflows/\(id)")
    }

    /// Duplicate a workflow.
    func duplicateWorkflow(_ id: String) async throws -> WorkflowResponse {
        return try await api.post("/workflows/\(id)/duplicate")
    }

    /// Rename a workflow (uses backend PATCH for partial update).
    func renameWorkflow(_ id: String, newName: String) async throws -> WorkflowResponse {
        let update = WorkflowPatchRequest(name: newName)
        return try await api.patch("/workflows/\(id)", body: update)
    }

    /// Update a workflow properties (name, description, folder_path).
    /// Uses PATCH for partial updates - only provided fields are changed.
    func updateWorkflowProperties(
        _ id: String,
        name: String? = nil,
        description: String? = nil,
        folderPath: String? = nil,
        sortOrder: Int? = nil
    ) async throws -> WorkflowResponse {
        let update = WorkflowPatchRequest(
            name: name,
            description: description,
            folderPath: folderPath,
            sortOrder: sortOrder
        )
        return try await api.patch("/workflows/\(id)", body: update)
    }

    /// Move workflow to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> WorkflowResponse {
        return try await updateWorkflowProperties(id, folderPath: folderPath)
    }

    /// Reorder workflows.
    func reorderWorkflows(_ workflowIds: [String], folderPath: String = "/") async throws {
        let request: ReorderRequest = ReorderRequest(workflowIds: workflowIds, folderPath: folderPath)
        try await api.postVoid("/workflows/reorder", body: request)
    }

    /// Import a workflow from JSON data.
    func importWorkflow(
        name: String = "",
        description: String = "",
        workflowData: [String: AnyCodable]
    ) async throws -> WorkflowResponse {
        let request = ImportWorkflowRequest(
            name: name,
            description: description,
            workflowData: workflowData
        )
        return try await api.post("/workflows/import", body: request)
    }

    /// Export a workflow as JSON data.
    func exportWorkflow(_ id: String) async throws -> [String: AnyCodable] {
        return try await api.get("/workflows/\(id)/export")
    }

    /// Run a saved workflow.
    func runSavedWorkflow(
        _ id: String,
        inputs: [String: Any] = [:],
        inputFiles: [String] = []
    ) async throws -> WorkflowRunResult {
        // First get the saved workflow
        let workflow = try await getWorkflow(id)

        let request = RunWorkflowRequest(
            workflow: workflow,
            inputs: inputs,
            inputFiles: inputFiles
        )
        return try await api.post("/workflows/\(id)/run", body: request)
    }
}

// MARK: - Response Models

// MARK: - Request Models

/// Request for partial workflow updates via PATCH.
struct WorkflowPatchRequest: Encodable {
    let name: String?
    let description: String?
    let folderPath: String?
    let sortOrder: Int?

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case folderPath = "folder_path"
        case sortOrder = "sort_order"
    }

    init(name: String? = nil, description: String? = nil, folderPath: String? = nil, sortOrder: Int? = nil) {
        self.name = name
        self.description = description
        self.folderPath = folderPath
        self.sortOrder = sortOrder
    }
}

struct ReorderRequest: Encodable {
    let workflowIds: [String]
    let folderPath: String

    enum CodingKeys: String, CodingKey {
        case workflowIds = "workflow_ids"
        case folderPath = "folder_path"
    }
}

struct ImportWorkflowRequest: Encodable {
    let name: String
    let description: String
    let workflowData: [String: AnyCodable]

    enum CodingKeys: String, CodingKey {
        case name, description
        case workflowData = "workflow_data"
    }
}

// MARK: - Additional Service Types

struct ToolsGroupedResponse: Codable {
    let categories: [CategoryTools]
}

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
