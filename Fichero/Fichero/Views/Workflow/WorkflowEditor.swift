import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowEditor")

/// Workflow editor content view - canvas with optional output log
/// This view goes in the content column, with WorkflowInspector in the detail column
struct WorkflowEditor: View {
    /// Reference to the selected workflow from sidebar (for display info)
    let selectedWorkflow: WorkflowSidebarItem?

    /// The actual workflow being edited
    @Binding var editingWorkflow: Workflow

    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State private var isRunning: Bool = false
    @State private var isSaving: Bool = false
    @State private var showOutputLog: Bool = false
    @State private var executionState: WorkflowExecutionState?

    // Canvas state (passed to WorkflowCanvasView)
    @State private var scale: CGFloat = 1.0
    @State private var snapToGrid: Bool = true

    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var workflowService: WorkflowService

    init(
        workflow: WorkflowSidebarItem?,
        editingWorkflow: Binding<Workflow>,
        displayMode: ViewDisplayMode = .icon
    ) {
        self.selectedWorkflow = workflow
        self._editingWorkflow = editingWorkflow
        self.displayMode = displayMode
    }

    var body: some View {
        VStack(spacing: 0) {
            // Workflow toolbar at top
            WorkflowToolbar(
                isRunning: $isRunning,
                showOutputLog: $showOutputLog,
                canRun: !editingWorkflow.nodes.isEmpty,
                scale: $scale,
                snapToGrid: $snapToGrid,
                onRun: runWorkflow,
                onSave: saveWorkflow,
                onExport: exportWorkflow,
                onResetZoom: resetZoom
            )

            // Canvas and output log
            VSplitView {
                // Main content area (adapts to displayMode)
                Group {
                    switch displayMode {
                    case .table:
                        workflowNodesTableView
                    default:
                        // Icon, List, Map all show canvas
                        WorkflowCanvasView(
                            workflow: $editingWorkflow,
                            scale: $scale,
                            snapToGrid: $snapToGrid
                        )
                    }
                }
                .frame(minHeight: 200)

                // Output log (collapsible, only during/after run)
                if showOutputLog {
                    WorkflowOutputLog(
                        workflow: editingWorkflow,
                        executionState: executionState
                    )
                    .frame(minHeight: 100, maxHeight: 250)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    // MARK: - Actions

    private func resetZoom() {
        withAnimation {
            scale = 1.0
        }
    }

    private func runWorkflow() {
        isRunning = true
        showOutputLog = true

        // Initialize execution state
        executionState = WorkflowExecutionState(
            status: .running,
            documentProgress: []
        )

        // Simulate workflow execution (will be replaced with API call)
        logger.info("Run workflow: \(editingWorkflow.name)")

        // Simulate completion after delay
        Task {
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            isRunning = false
            executionState?.status = .completed
        }
    }

    @MainActor
    private func saveWorkflow() async {
        logger.info("Save workflow: \(editingWorkflow.name)")
        do {
            let definition = editingWorkflow.toAPIFormat()
            if selectedWorkflow != nil {
                _ = try await workflowStore.updateWorkflow(definition)
            } else {
                _ = try await workflowStore.saveWorkflow(definition)
            }
        } catch {
            logger.error("Failed to save workflow: \(error.localizedDescription)")
        }
    }

    private func exportWorkflow() {
        logger.info("Export workflow: \(editingWorkflow.name)")
        Task {
            await WorkflowExporter.exportToFile(
                editingWorkflow.id,
                name: editingWorkflow.name,
                using: workflowService
            )
        }
    }

    // MARK: - Views

    private var workflowNodesTableView: some View {
        Table(editingWorkflow.nodes) {
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
}

// MARK: - Preview

#Preview {
    struct PreviewWrapper: View {
        @State private var workflow = Workflow(name: "Test Workflow", description: "A test workflow")

        var body: some View {
            NavigationSplitView {
                Text("Sidebar")
                    .frame(width: 200)
            } content: {
                WorkflowEditor(
                    workflow: nil,  // No sidebar selection in preview
                    editingWorkflow: $workflow
                )
            } detail: {
                WorkflowInspector(
                    workflow: $workflow,
                    onAddNode: { tool, position in
                        let newNode = WorkflowNode(from: tool, positionX: position.x, positionY: position.y)
                        workflow.nodes.append(newNode)
                    }
                )
                .frame(width: 280)
            }
        }
    }

    return PreviewWrapper()
        .frame(width: 1000, height: 600)
}
