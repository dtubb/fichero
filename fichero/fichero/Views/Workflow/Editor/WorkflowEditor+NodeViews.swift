import SwiftUI

extension WorkflowEditor {

    /// Icon grid view - shows nodes as cards in a grid
    var workflowNodesIconView: some View {
        Group {
            if editingWorkflow.nodes.isEmpty {
                ContentUnavailableView(
                    "No Nodes",
                    systemImage: "square.grid.2x2",
                    description: Text("Drag tools from the inspector to add nodes")
                )
            } else {
                ScrollView {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 140, maximum: 180), spacing: 16)],
                        spacing: 16
                    ) {
                        ForEach(editingWorkflow.nodes) { node in
                            WorkflowNodeCard(
                                node: node,
                                executionState: nodeStates[node.id]
                            )
                        }
                    }
                    .padding()
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }

    /// List view - shows nodes as rows in a list
    var workflowNodesListView: some View {
        let orderedNodes = orderedWorkflowNodes()

        return Group {
            if orderedNodes.isEmpty {
                ContentUnavailableView(
                    "No Nodes",
                    systemImage: "list.bullet",
                    description: Text("Drag tools from the inspector to add nodes")
                )
            } else {
                List(Array(orderedNodes.enumerated()), id: \.element.id) { index, node in
                    HStack(alignment: .center, spacing: 8) {
                        Text("\(index + 1).")
                            .font(.caption)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                            .frame(width: 28, alignment: .trailing)

                        WorkflowNodeRow(
                            node: node,
                            executionState: nodeStates[node.id]
                        )
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    // Returns nodes in execution order when the graph is acyclic; falls back
    // to visual order. Delegates to the shared WorkflowTopology so the list
    // numbering and the canvas step badges always agree (#4322).
    func orderedWorkflowNodes() -> [WorkflowNode] {
        WorkflowTopology.orderedNodes(nodes: editingWorkflow.nodes, edges: editingWorkflow.edges)
    }

    /// Table view - shows nodes in columns
    var workflowNodesTableView: some View {
        Table(editingWorkflow.nodes) {
            TableColumn("Status") { node in
                tableStatusCell(for: node)
            }
            .width(60)

            TableColumn("Tool") { node in
                Text(node.tool)
                    .font(.body)
            }
            .width(min: 100, ideal: 150)

            TableColumn("Label") { node in
                Text(node.label ?? "—")
                    .foregroundColor(.secondary)
            }
            .width(min: 100, ideal: 150)

            TableColumn("Position") { node in
                Text("(\(Int(node.positionX)), \(Int(node.positionY)))")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .width(min: 80, ideal: 100)

            TableColumn("Progress") { (node: WorkflowNode) in
                tableProgressCell(for: node)
            }
            .width(min: 80, ideal: 100)

            TableColumn("Inputs") { (node: WorkflowNode) in
                if node.inputMappings.isEmpty {
                    Text("—")
                        .foregroundColor(.secondary)
                } else {
                    Text("\(node.inputMappings.count) input(s)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .width(min: 80, ideal: 100)
        }
    }

    @ViewBuilder
    func tableStatusCell(for node: WorkflowNode) -> some View {
        if let state = nodeStates[node.id] {
            switch state.status {
            case .running, .parallelRunning:
                ProgressView()
                    .controlSize(.small)
            case .completed:
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
            case .failed:
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
            case .idle:
                Text("—")
                    .foregroundColor(.secondary)
            }
        } else {
            Text("—")
                .foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    func tableProgressCell(for node: WorkflowNode) -> some View {
        if let state = nodeStates[node.id], state.fileTotal > 0 {
            HStack(spacing: 4) {
                Text("\(state.successCount + state.errorCount)/\(state.fileTotal)")
                    .font(.caption)
                    .monospacedDigit()
                if state.errorCount > 0 {
                    Text("(\(state.errorCount) failed)")
                        .font(.caption2)
                        .foregroundColor(.red)
                }
            }
        } else {
            Text("—")
                .foregroundColor(.secondary)
        }
    }
}
