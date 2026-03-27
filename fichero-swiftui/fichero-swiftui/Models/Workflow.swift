import Foundation

/// Local workflow model for UI operations
struct Workflow: Identifiable, Codable {
    let id: String
    var name: String
    var description: String
    var provider: String
    var model: String
    var nodes: [WorkflowNode]
    var edges: [WorkflowEdge]
    var folderPath: String
    var sortOrder: Int
    var inputSource: WorkflowInputSource

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
        inputSource: WorkflowInputSource = .collection
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
    }

    /// Initialize from API response
    init(from apiWorkflow: WorkflowDefinition) {
        self.id = apiWorkflow.id
        self.name = apiWorkflow.name
        self.description = apiWorkflow.description
        self.provider = apiWorkflow.provider
        self.model = apiWorkflow.model
        self.nodes = apiWorkflow.nodes
        self.edges = apiWorkflow.edges
        self.folderPath = apiWorkflow.folderPath
        self.sortOrder = apiWorkflow.sortOrder
        self.inputSource = apiWorkflow.inputSource
    }

    /// Convert to API format for saving to backend
    func toAPIFormat() -> WorkflowDefinition {
        return WorkflowDefinition(
            id: self.id,
            name: self.name,
            description: self.description,
            provider: self.provider,
            model: self.model,
            nodes: self.nodes,
            edges: self.edges,
            folderPath: self.folderPath,
            sortOrder: self.sortOrder,
            inputSource: self.inputSource
        )
    }
}
