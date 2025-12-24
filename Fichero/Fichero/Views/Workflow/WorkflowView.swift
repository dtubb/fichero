import SwiftUI

/// Workflow editor content view - canvas with optional output log
/// This view goes in the content column, with WorkflowInspectorView in the detail column
struct WorkflowView: View {
    /// Reference to the selected workflow from sidebar (for display info)
    let selectedWorkflow: WorkflowSidebarItem?

    /// The actual workflow being edited
    @Binding var editingWorkflow: Workflow

    @State private var isRunning: Bool = false
    @State private var isSaving: Bool = false
    @State private var showOutputLog: Bool = false
    @State private var executionState: WorkflowExecutionState?

    @StateObject private var workflowStore = WorkflowStore()

    init(
        workflow: WorkflowSidebarItem?,
        editingWorkflow: Binding<Workflow>
    ) {
        self.selectedWorkflow = workflow
        self._editingWorkflow = editingWorkflow
    }

    var body: some View {
        VSplitView {
            // Main canvas area
            WorkflowCanvasView(
                workflow: $editingWorkflow
            )
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
        .toolbar {
            workflowToolbar
        }
    }

    // MARK: - Toolbar

    @ToolbarContentBuilder
    private var workflowToolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            // Toggle output log
            Button(action: { showOutputLog.toggle() }) {
                Image(systemName: showOutputLog ? "rectangle.bottomhalf.filled" : "rectangle.bottomhalf.inset.filled")
            }
            .help(showOutputLog ? "Hide Output Log" : "Show Output Log")

            Divider()

            // Save
            Button(action: {
                Task {
                    await saveWorkflow()
                }
            }) {
                Image(systemName: "square.and.arrow.down")
            }
            .help("Save Workflow")

            // Export
            Button(action: exportWorkflow) {
                Image(systemName: "square.and.arrow.up")
            }
            .help("Export Workflow")

            // Run button
            Button(action: runWorkflow) {
                if isRunning {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Image(systemName: "play.fill")
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
            .disabled(isRunning || editingWorkflow.nodes.isEmpty)
            .help(isRunning ? "Running..." : "Run Workflow")
        }
    }

    // MARK: - Actions

    private func runWorkflow() {
        isRunning = true
        showOutputLog = true

        // Initialize execution state
        executionState = WorkflowExecutionState(
            status: .running,
            documentProgress: []
        )

        // Simulate workflow execution (will be replaced with API call)
        print("Run workflow: \(editingWorkflow.name)")

        // Simulate completion after delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            isRunning = false
            executionState?.status = .completed
        }
    }

    @MainActor
    private func saveWorkflow() async {
        do {
            // Convert local workflow to API format and save to backend via WorkflowStore
            // TODO: Implement with proper workflow type once files are added to Xcode project
            print("Save workflow: \(editingWorkflow.name)")
            
            // Placeholder for actual implementation
            // let apiWorkflow = editingWorkflow.toAPIFormat()
            if selectedWorkflow != nil {
                _ = try await workflowStore.updateWorkflow(apiWorkflow)
            } else {
                _ = try await workflowStore.saveWorkflow(apiWorkflow)
            }
            
        } catch {
            print("Failed to save workflow: \(error)")
        }
    }

    private func exportWorkflow() {
        // TODO: Implement export when workflow type is available
        print("Export workflow: \(editingWorkflow.name)")
        // Will export workflow definition as JSON using WorkflowExporter
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
                WorkflowView(
                    workflow: nil,  // No sidebar selection in preview
                    editingWorkflow: $workflow
                )
            } detail: {
                WorkflowInspectorView(
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
