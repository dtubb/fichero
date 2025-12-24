import Foundation

/// Local workflow model for UI operations
struct Workflow: Identifiable, Codable {
    let id: String
    var name: String
    var description: String
    var nodes: [WorkflowNode]
    var edges: [WorkflowEdge]
    init(
        id: String = UUID().uuidString,
        name: String,
        description: String = "",
        nodes: [WorkflowNode] = [],
        edges: [WorkflowEdge] = []
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.nodes = nodes
        self.edges = edges
    }
    /// Initialize from API response
    init(from apiWorkflow: WorkflowDefinition) {
        self.id = apiWorkflow.id
        self.name = apiWorkflow.name
        self.description = apiWorkflow.description
        self.nodes = apiWorkflow.nodes
        self.edges = apiWorkflow.edges
    }
    /// Convert to API format
    func toAPIFormat() -> WorkflowDefinition {
        return WorkflowDefinition(
            id: self.id,
            name: self.name,
            description: self.description,
            provider: "openai", // default
            model: "gpt-4o",   // default
            nodes: self.nodes,
            edges: self.edges
        )
    }
}
