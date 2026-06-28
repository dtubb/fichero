import SwiftUI

/// Workflow editor content view - canvas with optional output log.
/// This view goes in the content column, with WorkflowInspector in the detail column.
struct WorkflowEditor: View {
    /// Reference to the selected workflow from sidebar (for display info)
    let selectedWorkflow: WorkflowSidebarItem?

    /// The actual workflow being edited
    @Binding var editingWorkflow: Workflow

    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    /// Document IDs currently selected in the library (plain UUIDs, no prefix)
    let selectedDocumentIds: [String]

    @State var isRunning: Bool = false
    @State var isSaving: Bool = false
    @State var saveError: String?
    @State var showSaveSuccess: Bool = false
    @State private var autosaveTask: Task<Void, Never>?

    // Canvas state (passed to WorkflowCanvasView)
    @State var scale: CGFloat = 1.0
    @State var snapToGrid: Bool = true

    // Diagram preview state
    @State var showDiagramPreview: Bool = false
    @State var diagramImage: PlatformImage?
    @State var diagramLoading: Bool = false
    @State var diagramError: String?

    // Document picker state
    @State var showDocumentPicker: Bool = false
    @State var showModelComparison: Bool = false

    @Environment(WorkflowStore.self) var workflowStore
    @EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @EnvironmentObject var libraryManager: LibraryManager
    @ObservedObject var featureManager = FeatureManager.shared

    // Uses @Observable pattern - injected via .environment() from LibraryWindow
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    // Not `private`: WorkflowEditor+Actions.runWorkflow() opens the Activity
    // window via this action, and Swift `private` blocks cross-file extension
    // access. Matches ContentView/LibraryView convention (#2328).
    @Environment(\.openWindow) var openWindow

    /// Node execution states for the editor's list/table/icon node views.
    ///
    /// Intentionally empty (#2546 / B2): run progress now lives ONLY in the
    /// Activity monitor, so the editor's node rows/cards/table cells stay in
    /// their idle state during a run — the editor is for editing, Activity is
    /// the single monitor. (`executionObserver` is still used to seed the
    /// run/compare sheets below.)
    var nodeStates: [String: NodeExecutionState] {
        [:]
    }

    init(
        workflow: WorkflowSidebarItem?,
        editingWorkflow: Binding<Workflow>,
        displayMode: ViewDisplayMode = .icon,
        selectedDocumentIds: [String] = []
    ) {
        self.selectedWorkflow = workflow
        self._editingWorkflow = editingWorkflow
        self.displayMode = displayMode
        self.selectedDocumentIds = selectedDocumentIds
    }

    var body: some View {
        VStack(spacing: 0) {
            // Workflow toolbar at top
            WorkflowToolbar(
                isRunning: $isRunning,
                canRun: !editingWorkflow.nodes.isEmpty,
                inputSource: $editingWorkflow.inputSource,
                onRun: runWorkflow,
                onImport: importWorkflow,
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
                },
                onCompareModels: {
                    showModelComparison = true
                }
            )

            // Canvas — run output surfaces in the Activity view (#2439)
            Group {
                switch displayMode {
                case .icon:
                    // Note: WorkflowCanvasView reads nodeStates from @Environment(WorkflowExecutionObserver.self)
                    WorkflowCanvasView(
                        workflow: $editingWorkflow,
                        scale: $scale,
                        snapToGrid: $snapToGrid
                    )
                case .list:
                    workflowNodesListView
                case .table:
                    if featureManager.isWorkflowEditorAdvancedViewsEnabled {
                        workflowNodesTableView
                    } else {
                        WorkflowCanvasView(
                            workflow: $editingWorkflow,
                            scale: $scale,
                            snapToGrid: $snapToGrid
                        )
                    }
                case .map:
                    // Keep map/table as advanced-mode fallback to avoid adding extra surface in 0.0.1.
                    WorkflowCanvasView(
                        workflow: $editingWorkflow,
                        scale: $scale,
                        snapToGrid: $snapToGrid
                    )
                case .realitykit:
                    // RealityKit is a Spatial mode, not a workflow-editor surface —
                    // fall back to the canvas like .map/.table.
                    WorkflowCanvasView(
                        workflow: $editingWorkflow,
                        scale: $scale,
                        snapToGrid: $snapToGrid
                    )
                case .spatial, .workspace:
                    // Collection-only stubs live at the library routing seam.
                    // In the workflow editor they fall back to the canvas like .map/.realitykit.
                    WorkflowCanvasView(
                        workflow: $editingWorkflow,
                        scale: $scale,
                        snapToGrid: $snapToGrid
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        // Saving is silent — no "Saved" flash/toast (#2438). Save failures still
        // surface via the alert below.
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
            .environment(executionObserver)
        }
        .sheet(isPresented: $showDocumentPicker) {
            DocumentPickerSheet(
                workflowId: editingWorkflow.id,
                workflowName: editingWorkflow.name
            )
            .environmentObject(libraryManager)
            .environment(documentStore)
            .environment(executionObserver)
        }
        .sheet(isPresented: $showModelComparison) {
            ModelComparisonView()
                .environment(executionObserver)
        }
        // Debounced autosave on any editingWorkflow change (#780). Without
        // this, model/provider selections in the node inspector live
        // in-memory only — never persisted to the engine — and are lost
        // on relaunch. 300ms debounce avoids saving on every keystroke
        // / drag tick while keeping the save responsive enough that the
        // user feels safe. (Tightened from 600ms — Daniel reported
        // model still resetting on restart, faster save = less window
        // for losing edits via popover-close races.)
        .task(id: editingWorkflow.id) {
            // Reset debounce when the user switches to a different workflow.
        }
        .onChange(of: editingWorkflow) { _, newValue in
            let firstNode = newValue.nodes.first
            actionsLogger.info("""
            [autosave] editingWorkflow changed — id=\(newValue.id), \
            nodes=\(newValue.nodes.count), \
            first node provider=\(firstNode?.providerName ?? "nil"), \
            model=\(firstNode?.modelName ?? "nil")
            """)
            autosaveTask?.cancel()
            autosaveTask = Task { @MainActor in
                try? await Task.sleep(for: .milliseconds(300))
                guard !Task.isCancelled else { return }
                actionsLogger.info("[autosave] firing saveWorkflow after debounce")
                await saveWorkflow()
            }
        }
    }
}
