import SwiftUI

/// Workflow editor content view - canvas with optional output log
/// This view goes in the content column, with WorkflowInspector in the detail column
struct WorkflowEditor: View {
    /// Reference to the selected workflow from sidebar (for display info)
    let selectedWorkflow: WorkflowSidebarItem?

    /// The actual workflow being edited
    @Binding var editingWorkflow: Workflow

    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State var isRunning: Bool = false
    @State var isSaving: Bool = false
    @State var saveError: String?
    @State var showSaveSuccess: Bool = false
    @State var showOutputLog: Bool = true
    @State var executionState: WorkflowExecutionState?

    // Canvas state (passed to WorkflowCanvasView)
    @State var scale: CGFloat = 1.0
    @State var snapToGrid: Bool = true

    // Diagram preview state
    @State var showDiagramPreview: Bool = false
    @State var diagramImage: NSImage?
    @State var diagramLoading: Bool = false
    @State var diagramError: String?

    // Document picker state
    @State var showDocumentPicker: Bool = false

    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var libraryManager: LibraryManager
    @ObservedObject var featureManager = FeatureManager.shared

    // Uses @Observable pattern - injected via .environment() from LibraryWindow
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Node execution states from the observer (single source of truth)
    var nodeStates: [String: NodeExecutionState] {
        executionObserver.activeExecutions[editingWorkflow.id]?.nodeStates ?? [:]
    }

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
                canRun: !editingWorkflow.nodes.isEmpty,
                onRun: runWorkflow,
                onExport: exportWorkflow,
                onPreviewDiagram: {
                    // Auto-save before showing diagram preview
                    Task { @MainActor in
                        await saveWorkflow()
                        showDiagramPreview = true
                    }
                },
                onRunOnDocuments: {
                    showDocumentPicker = true
                }
            )

            // Canvas and output log
            VSplitView {
                // Main content area (adapts to displayMode)
                Group {
                    if !featureManager.isWorkflowEditorAdvancedViewsEnabled {
                        // Note: WorkflowCanvasView reads nodeStates from @Environment(WorkflowExecutionObserver.self)
                        WorkflowCanvasView(
                            workflow: $editingWorkflow,
                            scale: $scale,
                            snapToGrid: $snapToGrid
                        )
                    } else {
                        switch displayMode {
                        case .icon:
                            workflowNodesIconView
                        case .list:
                            workflowNodesListView
                        case .table:
                            workflowNodesTableView
                        case .map:
                            // WorkflowCanvasView reads nodeStates from WorkflowExecutionObserver environment.
                            WorkflowCanvasView(
                                workflow: $editingWorkflow,
                                scale: $scale,
                                snapToGrid: $snapToGrid
                            )
                        }
                    }
                }
                .frame(minHeight: 200)

                // Output log is always visible in 0.0.1 workflow editor.
                WorkflowOutputLog(
                    workflow: editingWorkflow,
                    executionStateOverride: executionState
                )
                .frame(minHeight: 100, maxHeight: 250)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .overlay(alignment: .top) {
            // Save status indicator
            if showSaveSuccess {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Saved")
                        .font(.caption)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(.regularMaterial)
                .cornerRadius(8)
                .padding(.top, 50)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.2), value: showSaveSuccess)
        .alert("Save Failed", isPresented: Binding(
            get: { saveError != nil },
            set: { if !$0 { saveError = nil } }
        )) {
            Button("OK") { saveError = nil }
        } message: {
            if let error = saveError {
                Text(error)
            }
        }
        .sheet(isPresented: $showDiagramPreview) {
            WorkflowDiagramPreview(
                workflowId: editingWorkflow.id,
                workflowName: editingWorkflow.name,
                isPresented: $showDiagramPreview
            )
        }
        .sheet(isPresented: $showDocumentPicker) {
            DocumentPickerSheet(
                workflowId: editingWorkflow.id,
                workflowName: editingWorkflow.name
            )
            .environmentObject(libraryManager)
            .environmentObject(documentStore)
        }
    }
}
