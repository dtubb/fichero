import SwiftUI

/// Helper methods for node configuration views
/// These can be used by any view that has a `@Binding var node: WorkflowNode`
extension View {
    /// Helper to update a config value on a workflow node
    func updateNodeConfig(_ node: Binding<WorkflowNode>, key: String, value: AnyCodableValue) {
        if node.wrappedValue.config == nil {
            node.wrappedValue.config = [:]
        }
        node.wrappedValue.config?[key] = value
    }

    /// Helper to remove a config value from a workflow node
    func removeNodeConfig(_ node: Binding<WorkflowNode>, key: String) {
        node.wrappedValue.config?.removeValue(forKey: key)
    }
}
