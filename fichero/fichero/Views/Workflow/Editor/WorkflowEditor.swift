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

    /// A resolved run scope that would WIDEN beyond the user's selection,
    /// parked here until they confirm or cancel (#4396 ask #3 / #4523).
    /// `WorkflowRunScope` has carried `widensBeyondSelection` since the #4396
    /// fix precisely so callers could ask first — but nothing ever consulted
    /// it, so a run with nothing selected silently expanded to the whole
    /// folder, billing per page across documents the user never chose. The
    /// run this holds is dispatched ONLY via `confirmPendingWideningRun()`.
    @State var pendingWideningScope: WorkflowRunScope.Resolution?

    // Undo support for toolbar-level workflow mutations (Tidy, #4323).
    @State private var editorUndoProxy = WorkflowUndoProxy()
    @Environment(\.undoManager) private var undoManager

    @Environment(WorkflowStore.self) var workflowStore
    @Environment(WorkflowService.self) var workflowService
    @Environment(WorkflowStreamService.self) var workflowStreamService
    @Environment(DocumentStore.self) var documentStore: DocumentStore
    @Environment(LibraryManager.self) var libraryManager
    @Environment(FeatureManager.self) var featureManager

    // Uses @Observable pattern - injected via .environment() from LibraryWindow
    @Environment(WorkflowExecutionObserver.self) var executionObserver
    // Not `private`: WorkflowEditor+Actions.runWorkflow() opens the Activity
    // window via this action, and Swift `private` blocks cross-file extension
    // access. Matches ContentView/LibraryView convention (#2328).
    @Environment(\.openWindow) var openWindow
    @Environment(\.supportsMultipleWindows) var supportsMultipleWindows

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
                case .columns, .dataset, .canvas, .space, .workspace:
                    // Columns/Canvas/Space/Workspace aren't distinct workflow-
                    // editor surfaces — they fall back to the workflow canvas
                    // (#3081; columns is library-only, #4160 step 4).
                    WorkflowCanvasView(
                        workflow: $editingWorkflow,
                        scale: $scale,
                        snapToGrid: $snapToGrid
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // No-silent-fallback (F7): if a running workflow's event stream drops,
            // the canvas would otherwise look stalled — surface it. Informational
            // (no reconnect button): the run may still be completing server-side,
            // and re-subscribing is driven by re-opening / re-running the run.
            .overlay(alignment: .top) {
                if workflowStreamService.liveUpdatesUnavailable {
                    LiveUpdatesPausedPill(onReconnect: nil)
                }
            }

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
                },
                onTidy: tidyLayout,
                showImportExport: featureManager.isWorkflowImportExportEnabled,
                showLangGraphPreview: featureManager.isWorkflowLangGraphPreviewEnabled,
                showFilesToolbarButton: featureManager.isWorkflowFilesToolbarButtonEnabled
            )
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
            .environment(libraryManager)
            .environment(documentStore)
            .environment(executionObserver)
        }
        .sheet(isPresented: $showModelComparison) {
            ModelComparisonView()
                .environment(executionObserver)
        }
        // The scope gate (#4396 ask #3 / #4523): a run that would reach beyond
        // the selection states its scope and waits for consent. Dismissing any
        // other way (esc, click-outside) cancels — the widened run never
        // starts by default.
        .confirmationDialog(
            "Run “\(editingWorkflow.name)” on \(pendingWideningScope?.describedScope ?? "this folder")?",
            isPresented: Binding(
                get: { pendingWideningScope != nil },
                set: { if !$0 { pendingWideningScope = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Run on Everything in This Folder", role: .destructive) {
                confirmPendingWideningRun()
            }
            Button("Cancel", role: .cancel) {
                pendingWideningScope = nil
            }
        } message: {
            Text(
                """
                Nothing is selected, so this will run on every document in the \
                current folder — not a selection. Steps that use vision or \
                language models can bill for each page they process.
                """
            )
        }
        // Debounced autosave on any editingWorkflow change (#780). Without
        // this, model/provider selections in the node inspector live
        // in-memory only — never persisted to the engine — and are lost
        // on relaunch. 300ms debounce avoids saving on every keystroke
        // / drag tick while keeping the save responsive enough that the
        // user feels safe. (Tightened from 600ms — the user reported
        // model still resetting on restart, faster save = less window
        // for losing edits via popover-close races.)
        .task(id: editingWorkflow.id) {
            // Reset debounce when the user switches to a different workflow.
        }
        .onAppear {
            let binding = $editingWorkflow
            editorUndoProxy.apply = { restored in
                binding.wrappedValue = restored
            }
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

    /// Re-lay the graph left-to-right by execution order (#4323).
    /// Pure layout math in WorkflowTidyLayout; this applies it with undo.
    private func tidyLayout() {
        let previousWorkflow = editingWorkflow
        let targets = WorkflowTidyLayout.positions(
            nodes: editingWorkflow.nodes,
            edges: editingWorkflow.edges
        )
        guard !targets.isEmpty else { return }

        withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
            for index in editingWorkflow.nodes.indices {
                guard let target = targets[editingWorkflow.nodes[index].id] else { continue }
                editingWorkflow.nodes[index].positionX = target.x
                editingWorkflow.nodes[index].positionY = target.y
            }
        }

        guard previousWorkflow != editingWorkflow else { return }
        editorUndoProxy.registerTransition(
            from: editingWorkflow,
            to: previousWorkflow,
            actionName: "Tidy Layout",
            undoManager: undoManager
        )
    }
}
