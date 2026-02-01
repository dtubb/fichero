import SwiftUI
import OSLog

// swiftlint:disable file_length

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowEditor")

// TODO: Refactor WorkflowEditor - extract canvas and output sections
// File is 1002 lines, target <1000. Type body is 397 lines, target <350

/// Workflow editor content view - canvas with optional output log
/// This view goes in the content column, with WorkflowInspector in the detail column
// swiftlint:disable:next type_body_length
struct WorkflowEditor: View {
    /// Reference to the selected workflow from sidebar (for display info)
    let selectedWorkflow: WorkflowSidebarItem?

    /// The actual workflow being edited
    @Binding var editingWorkflow: Workflow

    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State private var isRunning: Bool = false
    @State private var isSaving: Bool = false
    @State private var saveError: String?
    @State private var showSaveSuccess: Bool = false
    @State private var showOutputLog: Bool = false
    @State private var executionState: WorkflowExecutionState?

    // Canvas state (passed to WorkflowCanvasView)
    @State private var scale: CGFloat = 1.0
    @State private var snapToGrid: Bool = true

    // Diagram preview state
    @State private var showDiagramPreview: Bool = false
    @State private var diagramImage: NSImage?
    @State private var diagramLoading: Bool = false
    @State private var diagramError: String?

    // Document picker state
    @State private var showDocumentPicker: Bool = false

    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
    @EnvironmentObject var workflowStreamService: WorkflowStreamService
    @EnvironmentObject var documentStore: DocumentStore
    @EnvironmentObject var libraryManager: LibraryManager

    // Uses @Observable pattern - injected via .environment() from LibraryWindow
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Node execution states from the observer (single source of truth)
    private var nodeStates: [String: NodeExecutionState] {
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
                isSaving: $isSaving,
                showOutputLog: $showOutputLog,
                canRun: !editingWorkflow.nodes.isEmpty,
                scale: $scale,
                snapToGrid: $snapToGrid,
                onRun: runWorkflow,
                onSave: saveWorkflow,
                onExport: exportWorkflow,
                onResetZoom: resetZoom,
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
                    switch displayMode {
                    case .icon:
                        workflowNodesIconView
                    case .list:
                        workflowNodesListView
                    case .table:
                        workflowNodesTableView
                    case .map:
                        // Map view shows the spatial canvas
                        // Note: WorkflowCanvasView reads nodeStates from @Environment(WorkflowExecutionObserver.self)
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
                        executionStateOverride: executionState
                    )
                    .frame(minHeight: 100, maxHeight: 250)
                }
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

    // MARK: - Actions

    private func resetZoom() {
        withAnimation {
            scale = 1.0
        }
    }

    // swiftlint:disable:next function_body_length
    private func runWorkflow() {
        isRunning = true
        showOutputLog = true

        // Initialize execution state (will be updated from observer)
        executionState = WorkflowExecutionState(
            status: .running,
            documentProgress: []
        )

        logger.info("Run workflow: \(editingWorkflow.name)")

        Task { @MainActor in
            do {
                // IMPORTANT: Save workflow before running to ensure backend has latest version
                logger.info("Auto-saving workflow before execution...")
                let definition = editingWorkflow.toAPIFormat()

                // Debug: Log what we're sending to backend
                logger.info("[DEBUG] Workflow: id=\(definition.id), nodes=\(definition.nodes.count)")
                for node in definition.nodes {
                    let configDesc = node.config?.keys.joined(separator: ", ") ?? "nil"
                    logger.info("[DEBUG] Node \(node.tool): config keys=[\(configDesc)]")
                }

                if selectedWorkflow != nil {
                    _ = try await workflowStore.updateWorkflow(definition)
                } else {
                    _ = try await workflowStore.saveWorkflow(definition)
                }
                logger.info("Workflow saved, now executing with SSE streaming...")

                // Execute workflow with NEW non-blocking API + SSE subscription
                // Single source of truth: all events go through executionObserver
                let workflowId = editingWorkflow.id  // Capture ID before closure

                // Track completion with a continuation
                var streamCompleted = false

                let response = try await workflowStreamService.execute(
                    workflowId: workflowId,
                    inputs: [:],
                    onEvent: { [weak documentStore] event in
                        // Debug: Log every event (using info level for visibility)
                        let eventDesc = String(String(describing: event).prefix(100))
                        logger.info("[SSE] Event: \(eventDesc)")

                        // Update global observer (single source of truth for all UI)
                        executionObserver.handleEvent(event, for: workflowId)

                        // Debug: Log document progress count
                        if let exec = executionObserver.activeExecutions[workflowId] {
                            logger.info("[SSE] Document count: \(exec.documentProgress.count), nodeStates: \(exec.nodeStates.count)")
                        }

                        // Update executionState from observer (for output log)
                        executionState = executionObserver.getExecutionState(for: workflowId)

                        // Update document processing status in library view
                        updateDocumentStatus(for: event, documentStore: documentStore)

                        // Track terminal events
                        switch event {
                        case .complete, .error, .systemicError:
                            streamCompleted = true
                        default:
                            break
                        }
                    }
                )

                logger.info("[SSE] Workflow started with thread: \(response.threadId)")

                // Register with global observer for app-wide visibility (with real thread ID)
                let threadId = response.threadId
                executionObserver.startExecution(
                    workflowId: workflowId,
                    name: editingWorkflow.name,
                    threadId: threadId,
                    onCancel: { [weak workflowStreamService] in
                        Task { @MainActor in
                            try? await workflowStreamService?.stopWorkflow(threadId: threadId)
                        }
                    }
                )

                // Wait for stream to complete (poll observer state)
                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(100))
                    // Check if we're cancelled
                    if Task.isCancelled { break }
                    // Also check observer for completion
                    if let exec = executionObserver.activeExecutions[workflowId],
                       !exec.isRunning {
                        streamCompleted = true
                    }
                }

                // Determine final status from observer
                logger.info("[SSE] Stream ended, checking final state for workflowId: \(workflowId)")
                if let exec = executionObserver.activeExecutions[workflowId] {
                    logger.info("[SSE] Final documentProgress: \(exec.documentProgress.count), error: \(exec.workflowError ?? "none")")
                    for (_, progress) in exec.documentProgress {
                        logger.info("[SSE] Document: \(progress.documentName), statuses: \(progress.stepStatuses.count)")
                    }
                } else {
                    logger.warning("[SSE] No execution found for workflowId: \(workflowId)")
                }

                let finalStatus: WorkflowStatus
                if let execution = executionObserver.activeExecutions[workflowId] {
                    if execution.workflowError != nil {
                        finalStatus = .failed
                        logger.error("Workflow failed: \(execution.workflowError ?? "Unknown error")")
                    } else {
                        finalStatus = execution.status == .failed ? .failed : .completed
                        if finalStatus == .completed {
                            logger.info("Workflow completed successfully")
                        }
                    }
                } else {
                    finalStatus = .completed
                }

                // Final update of execution state from observer (with document progress)
                if var finalState = executionObserver.getExecutionState(for: workflowId) {
                    finalState.status = finalStatus
                    let statusStr = String(describing: finalStatus)
                    logger.info("[SSE] Final state: \(finalState.documentProgress.count) docs, status: \(statusStr), error: \(finalState.error ?? "none")")
                    executionState = finalState
                } else {
                    logger.warning("[SSE] No final state from observer, keeping current executionState")
                    executionState?.status = finalStatus
                }

                // End tracking in global observer
                executionObserver.endExecution(workflowId: workflowId, status: finalStatus)

            } catch {
                logger.error("Failed to execute workflow: \(error.localizedDescription)")
                executionState?.status = .failed
                executionState?.error = error.localizedDescription

                // End tracking with failed status
                executionObserver.endExecution(workflowId: editingWorkflow.id, status: .failed)
            }

            isRunning = false
        }
    }

    /// Update document processing status in library based on stream events
    private func updateDocumentStatus(for event: WorkflowStreamEvent, documentStore: DocumentStore?) {
        guard let documentStore = documentStore else { return }

        switch event {
        case .fileStart(_, _, let filePath, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .processing)

        case .fileComplete(_, _, let filePath, _, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .completed)

        case .fileError(_, _, let filePath, _, _):
            documentStore.updateProcessingStatus(forPath: filePath, status: .failed)

        default:
            break
        }
    }

    @MainActor
    private func saveWorkflow() async {
        logger.info("Save workflow: \(editingWorkflow.name)")
        isSaving = true
        saveError = nil

        do {
            let definition = editingWorkflow.toAPIFormat()
            if selectedWorkflow != nil {
                _ = try await workflowStore.updateWorkflow(definition)
            } else {
                _ = try await workflowStore.saveWorkflow(definition)
            }
            logger.info("Successfully saved workflow")
            showSaveSuccess = true

            // Hide success message after 2 seconds
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { return }
                showSaveSuccess = false
            }
        } catch {
            logger.error("Failed to save workflow: \(error.localizedDescription)")
            saveError = error.localizedDescription
        }

        isSaving = false
    }

    private func exportWorkflow() {
        logger.info("Export workflow: \(editingWorkflow.name)")
        Task { @MainActor in
            await WorkflowExporter.exportToFile(
                editingWorkflow.id,
                name: editingWorkflow.name,
                using: workflowServiceGenerated
            )
        }
    }

    // MARK: - Views

    /// Icon grid view - shows nodes as cards in a grid
    private var workflowNodesIconView: some View {
        Group {
            if editingWorkflow.nodes.isEmpty {
                ContentUnavailableView(
                    "No Nodes",
                    systemImage: "square.grid.2x2",
                    description: Text("Drag tools from the inspector to add nodes")
                )
            } else {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 140, maximum: 180), spacing: 16)], spacing: 16) {
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
    private var workflowNodesListView: some View {
        Group {
            if editingWorkflow.nodes.isEmpty {
                ContentUnavailableView(
                    "No Nodes",
                    systemImage: "list.bullet",
                    description: Text("Drag tools from the inspector to add nodes")
                )
            } else {
                List(editingWorkflow.nodes) { node in
                    WorkflowNodeRow(
                        node: node,
                        executionState: nodeStates[node.id]
                    )
                }
                .listStyle(.plain)
            }
        }
    }

    /// Table view - shows nodes in columns
    private var workflowNodesTableView: some View {
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
    private func tableStatusCell(for node: WorkflowNode) -> some View {
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
    private func tableProgressCell(for node: WorkflowNode) -> some View {
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

// MARK: - Node Card (for Icon view)

/// Card representation of a workflow node for Icon view
private struct WorkflowNodeCard: View {
    let node: WorkflowNode
    var executionState: NodeExecutionState?

    var body: some View {
        VStack(spacing: 8) {
            // Icon with execution state overlay
            ZStack {
                Image(systemName: iconForTool(node.tool))
                    .font(.system(size: 32))
                    .foregroundStyle(colorForTool(node.tool))
                    .frame(width: 50, height: 50)
                    .background(colorForTool(node.tool).opacity(0.15))
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                // Execution state overlay
                if let state = executionState {
                    executionOverlay(for: state)
                }
            }

            // Label
            Text(node.label ?? node.tool)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            // Tool type
            Text(node.tool)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(width: 140, height: 120)
        .padding(8)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(.separatorColor), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.15), radius: 3, x: 0, y: 2)
    }

    private func iconForTool(_ tool: String) -> String {
        switch tool.lowercased() {
        case "files", "collection", "search": return "doc.on.doc"
        case "describe", "analyze": return "eye"
        case "transcribe": return "waveform"
        case "summarize", "translate", "classify": return "text.bubble"
        case "enhance", "crop", "rotate", "segment": return "wand.and.stars"
        case "to_pdf", "to_word", "to_excel", "to_json": return "arrow.triangle.2.circlepath"
        case "if", "switch": return "questionmark.diamond"
        case "loop", "merge": return "arrow.triangle.branch"
        case "agent": return "brain"
        default: return "gearshape"
        }
    }

    private func colorForTool(_ tool: String) -> Color {
        switch tool.lowercased() {
        case "files", "collection", "search": return .green
        case "describe", "analyze", "transcribe": return .blue
        case "summarize", "translate", "classify": return .purple
        case "enhance", "crop", "rotate", "segment": return .orange
        case "to_pdf", "to_word", "to_excel", "to_json": return .cyan
        case "if", "switch", "loop", "merge": return .yellow
        case "agent": return .pink
        default: return .gray
        }
    }

    @ViewBuilder
    private func executionOverlay(for state: NodeExecutionState) -> some View {
        VStack {
            Spacer()
            HStack {
                Spacer()
                switch state.status {
                case .running, .parallelRunning:
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.7)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .completed:
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .failed:
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.red)
                        .padding(4)
                        .background(.ultraThickMaterial)
                        .clipShape(Circle())
                case .idle:
                    EmptyView()
                }
            }
        }
    }
}

// MARK: - Node Row (for List view)

/// Row representation of a workflow node for List view
private struct WorkflowNodeRow: View {
    let node: WorkflowNode
    var executionState: NodeExecutionState?

    var body: some View {
        HStack(spacing: 12) {
            // Icon with execution indicator
            ZStack {
                Image(systemName: iconForTool(node.tool))
                    .font(.title2)
                    .foregroundStyle(colorForTool(node.tool))
                    .frame(width: 36, height: 36)
                    .background(colorForTool(node.tool).opacity(0.15))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                // Execution state indicator
                if let state = executionState, state.status != .idle {
                    VStack {
                        Spacer()
                        HStack {
                            Spacer()
                            executionBadge(for: state)
                        }
                    }
                }
            }
            .frame(width: 36, height: 36)

            // Info
            VStack(alignment: .leading, spacing: 2) {
                Text(node.label ?? node.tool)
                    .font(.body)
                    .fontWeight(.medium)

                HStack(spacing: 8) {
                    Text(node.tool)
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    if !node.inputMappings.isEmpty {
                        Text("•")
                            .foregroundStyle(.tertiary)
                        Text("\(node.inputMappings.count) input(s)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    // Show progress for parallel execution
                    if let state = executionState, state.fileTotal > 0 {
                        Text("•")
                            .foregroundStyle(.tertiary)
                        Text("\(state.successCount + state.errorCount)/\(state.fileTotal)")
                            .font(.caption)
                            .foregroundStyle(.blue)
                    }
                }
            }

            Spacer()

            // Position badge
            Text("(\(Int(node.positionX)), \(Int(node.positionY)))")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(.quaternary)
                .clipShape(Capsule())
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func executionBadge(for state: NodeExecutionState) -> some View {
        switch state.status {
        case .running, .parallelRunning:
            ProgressView()
                .controlSize(.mini)
                .scaleEffect(0.7)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .font(.caption2)
                .foregroundColor(.green)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .font(.caption2)
                .foregroundColor(.red)
        case .idle:
            EmptyView()
        }
    }

    private func iconForTool(_ tool: String) -> String {
        switch tool.lowercased() {
        case "files", "collection", "search": return "doc.on.doc"
        case "describe", "analyze": return "eye"
        case "transcribe": return "waveform"
        case "summarize", "translate", "classify": return "text.bubble"
        case "enhance", "crop", "rotate", "segment": return "wand.and.stars"
        case "to_pdf", "to_word", "to_excel", "to_json": return "arrow.triangle.2.circlepath"
        case "if", "switch": return "questionmark.diamond"
        case "loop", "merge": return "arrow.triangle.branch"
        case "agent": return "brain"
        default: return "gearshape"
        }
    }

    private func colorForTool(_ tool: String) -> Color {
        switch tool.lowercased() {
        case "files", "collection", "search": return .green
        case "describe", "analyze", "transcribe": return .blue
        case "summarize", "translate", "classify": return .purple
        case "enhance", "crop", "rotate", "segment": return .orange
        case "to_pdf", "to_word", "to_excel", "to_json": return .cyan
        case "if", "switch", "loop", "merge": return .yellow
        case "agent": return .pink
        default: return .gray
        }
    }
}

// MARK: - Workflow Diagram Preview

/// Sheet view showing the LangGraph visualization and Python code for a workflow
struct WorkflowDiagramPreview: View {
    let workflowId: String
    let workflowName: String
    @Binding var isPresented: Bool

    @EnvironmentObject var apiClient: APIClient

    @State private var diagramImage: NSImage?
    @State private var pythonCode: String?
    @State private var isLoading: Bool = true
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Workflow Diagram & Code")
                    .font(.headline)

                Spacer()

                Text(workflowName)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button("Done") {
                    isPresented = false
                }
                .keyboardShortcut(.escape)
            }
            .padding()
            .background(.bar)

            Divider()

            // Content - split view with diagram on left, code on right
            if isLoading {
                ProgressView("Loading diagram and code...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 48))
                        .foregroundStyle(.orange)
                    Text("Failed to load")
                        .font(.headline)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") {
                        Task { @MainActor in
                            await loadContent()
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    // Left: Diagram
                    VStack(spacing: 0) {
                        Text("LangGraph Diagram")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.bar)

                        if let image = diagramImage {
                            ScrollView([.horizontal, .vertical]) {
                                Image(nsImage: image)
                                    .resizable()
                                    .aspectRatio(contentMode: .fit)
                                    .padding()
                            }
                            .background(Color(nsColor: .textBackgroundColor))
                        } else {
                            VStack {
                                Image(systemName: "flowchart")
                                    .font(.largeTitle)
                                    .foregroundStyle(.secondary)
                                Text("No diagram")
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }
                    .frame(minWidth: 300)

                    // Right: Python Code
                    VStack(spacing: 0) {
                        HStack {
                            Text("Generated Python Code")
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            Spacer()

                            if pythonCode != nil {
                                Button {
                                    if let code = pythonCode {
                                        NSPasteboard.general.clearContents()
                                        NSPasteboard.general.setString(code, forType: .string)
                                    }
                                } label: {
                                    Image(systemName: "doc.on.doc")
                                }
                                .buttonStyle(.plain)
                                .help("Copy to clipboard")
                            }
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(.bar)

                        if let code = pythonCode {
                            ScrollView {
                                Text(code)
                                    .font(.system(.caption, design: .monospaced))
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(8)
                            }
                            .background(Color(nsColor: .textBackgroundColor))
                        } else {
                            VStack {
                                Image(systemName: "chevron.left.forwardslash.chevron.right")
                                    .font(.largeTitle)
                                    .foregroundStyle(.secondary)
                                Text("No code")
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    }
                    .frame(minWidth: 400)
                }
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .task {
            guard !Task.isCancelled else { return }
            await loadContent()
        }
    }

    private func loadContent() async {
        isLoading = true
        error = nil

        // Load diagram and code in parallel
        async let diagramTask: Void = loadDiagram()
        async let codeTask: Void = loadCode()

        await diagramTask
        await codeTask

        isLoading = false
    }

    private func loadDiagram() async {
        do {
            let url = apiClient.baseURL
                .appendingPathComponent("workflow-execution")
                .appendingPathComponent("workflows")
                .appendingPathComponent(workflowId)
                .appendingPathComponent("visualization.png")

            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            if let libraryPath = apiClient.currentLibraryPath {
                request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
            }

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                return
            }
            diagramImage = NSImage(data: data)
        } catch {
            // Diagram loading failure is not fatal
        }
    }

    private func loadCode() async {
        do {
            let url = apiClient.baseURL
                .appendingPathComponent("workflow-execution")
                .appendingPathComponent("workflows")
                .appendingPathComponent(workflowId)
                .appendingPathComponent("code")

            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            if let libraryPath = apiClient.currentLibraryPath {
                request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
            }

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                if let errorJson = try? JSONDecoder().decode([String: String].self, from: data),
                   let detail = errorJson["detail"] {
                    self.error = detail
                }
                return
            }

            // Parse JSON response
            struct CodeResponse: Codable {
                let pythonCode: String

                enum CodingKeys: String, CodingKey {
                    case pythonCode = "python_code"
                }
            }
            if let codeResponse = try? JSONDecoder().decode(CodeResponse.self, from: data) {
                pythonCode = codeResponse.pythonCode
            }
        } catch {
            // Code loading failure sets error only if diagram also failed
            if diagramImage == nil {
                self.error = error.localizedDescription
            }
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
