import SwiftUI
import OSLog
import FicheroAPIClient

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowLibraryView")

/// Tab selection for workflow library
enum WorkflowLibraryTab: String, CaseIterable {
    case workflows = "Workflows"
    case chains = "Chains"
}

/// View for browsing and managing saved workflows and workflow chains
struct WorkflowLibraryView: View {
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var apiClient: APIClient
    @State private var selectedTab: WorkflowLibraryTab = .workflows

    /// View display mode from toolbar (icon, list, table, map)
    let displayMode: ViewDisplayMode

    /// Callback when user wants to open a workflow in the editor
    var onOpenWorkflow: ((WorkflowSidebarItem) -> Void)?

    var body: some View {
        VStack(spacing: 0) {
            // Tab picker
            Picker("View", selection: $selectedTab) {
                ForEach(WorkflowLibraryTab.allCases, id: \.self) { tab in
                    Text(tab.rawValue).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.vertical, 8)

            // Content based on selected tab
            switch selectedTab {
            case .workflows:
                WorkflowListView(displayMode: displayMode, onOpenWorkflow: onOpenWorkflow)
            case .chains:
                WorkflowChainListView(apiClient: apiClient)
            }
        }
    }
}

/// View for browsing and managing saved workflows
struct WorkflowListView: View {
    @EnvironmentObject var workflowStore: WorkflowStore
    @EnvironmentObject var workflowServiceGenerated: WorkflowServiceGenerated
    @State private var searchText = ""
    @State private var selectedWorkflowId: String?
    @State private var selectedWorkflowIds: Set<String> = []
    @State private var showNewWorkflowSheet = false
    @State private var showDeleteConfirmation = false
    @State private var workflowToDelete: WorkflowSidebarItem?
    @State private var isLoading = false
    @State private var tableSortOrder = [KeyPathComparator(\WorkflowSidebarItem.name)]
    @State private var isImporting = false

    /// View display mode from toolbar
    let displayMode: ViewDisplayMode

    /// Callback when user wants to open a workflow in the editor
    var onOpenWorkflow: ((WorkflowSidebarItem) -> Void)?

    var body: some View {
        workflowContent
        .searchable(text: $searchText, prompt: "Search workflows...")
        .task {
            guard !Task.isCancelled else { return }
            await loadWorkflows()
        }
        .sheet(isPresented: $showNewWorkflowSheet) {
            NewWorkflowSheet { name, description in
                await createWorkflow(name: name, description: description)
            }
        }
        .alert("Delete Workflow?", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) {
                workflowToDelete = nil
            }
            Button("Delete", role: .destructive) {
                if let workflow = workflowToDelete {
                    Task { await deleteWorkflow(workflow) }
                }
            }
        } message: {
            if let workflow = workflowToDelete {
                Text("Are you sure you want to delete \"\(workflow.name)\"? This action cannot be undone.")
            }
        }
    }

    // MARK: - Content Views Based on Display Mode

    @ViewBuilder
    private var workflowContent: some View {
        Group {
            if isLoading && workflowStore.workflows.isEmpty {
                ProgressView("Loading workflows...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredWorkflows.isEmpty {
                emptyStateView
            } else {
                switch displayMode {
                case .icon:
                    iconGridView
                case .list:
                    listView
                case .table:
                    tableView
                case .map:
                    // Map mode shows the same as list for workflows
                    listView
                }
            }
        }
        .navigationTitle("Workflow Library")
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    showNewWorkflowSheet = true
                } label: {
                    Image(systemName: "plus")
                }
                .help("Create new workflow")

                Button {
                    importWorkflow()
                } label: {
                    Image(systemName: "square.and.arrow.down")
                }
                .disabled(isImporting)
                .help("Import workflow from JSON file")
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await loadWorkflows() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
                .help("Refresh workflow list")
            }
        }
    }

    // MARK: - Icon Grid View

    private var iconGridView: some View {
        ScrollView {
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 140, maximum: 180))],
                alignment: .center,
                spacing: 16
            ) {
                ForEach(filteredWorkflows) { workflow in
                    WorkflowThumbnailView(
                        workflow: workflow,
                        isSelected: selectedWorkflowId == workflow.id
                    )
                    .onTapGesture {
                        selectedWorkflowId = workflow.id
                    }
                    .onTapGesture(count: 2) {
                        openWorkflow(workflow)
                    }
                    .contextMenu {
                        workflowContextMenu(for: workflow)
                    }
                }
            }
            .padding()
        }
    }

    // MARK: - List View

    private var listView: some View {
        List(filteredWorkflows, selection: $selectedWorkflowId) { workflow in
            WorkflowLibraryRow(workflow: workflow)
                .tag(workflow.id)
                .contextMenu {
                    workflowContextMenu(for: workflow)
                }
        }
    }

    // MARK: - Table View

    private var tableView: some View {
        Table(filteredWorkflows, selection: $selectedWorkflowIds, sortOrder: $tableSortOrder) {
            TableColumn("Name", value: \.name) { workflow in
                HStack {
                    Image(systemName: "flowchart")
                        .foregroundColor(.accentColor)
                    Text(workflow.name)
                }
            }
            .width(min: 150, ideal: 200)

            TableColumn("Description") { workflow in
                Text(workflow.description ?? "—")
                    .foregroundColor(.secondary)
            }
            .width(min: 100, ideal: 200)

            TableColumn("Nodes", value: \.nodeCount) { workflow in
                Text("\(workflow.nodeCount)")
                    .monospacedDigit()
            }
            .width(60)

            TableColumn("Connections", value: \.edgeCount) { workflow in
                Text("\(workflow.edgeCount)")
                    .monospacedDigit()
            }
            .width(80)

            TableColumn("Updated") { workflow in
                Text(workflow.updatedAt, style: .date)
                    .foregroundColor(.secondary)
            }
            .width(min: 80, ideal: 100)
        }
        .tableStyle(.inset)
        .onChange(of: selectedWorkflowIds) { _, newValue in
            // Sync table selection to single selection for detail view
            selectedWorkflowId = newValue.first
        }
        .onChange(of: tableSortOrder) { _, newOrder in
            // TableColumn sorting requires sortable workflows
        }
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        ContentUnavailableView {
            Label("No Workflows", systemImage: "flowchart")
        } description: {
            if searchText.isEmpty {
                Text("Create your first workflow to get started")
            } else {
                Text("No workflows match your search")
            }
        } actions: {
            if searchText.isEmpty {
                Button("New Workflow") {
                    showNewWorkflowSheet = true
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }

    // MARK: - Context Menu

    @ViewBuilder
    private func workflowContextMenu(for workflow: WorkflowSidebarItem) -> some View {
        Button {
            openWorkflow(workflow)
        } label: {
            Label("Edit", systemImage: "pencil")
        }

        Button {
            duplicateWorkflow(workflow)
        } label: {
            Label("Duplicate", systemImage: "doc.on.doc")
        }

        Button {
            exportWorkflow(workflow)
        } label: {
            Label("Export to JSON...", systemImage: "square.and.arrow.up")
        }

        Divider()

        Button(role: .destructive) {
            confirmDelete(workflow)
        } label: {
            Label("Delete", systemImage: "trash")
        }
    }

    private var filteredWorkflows: [WorkflowSidebarItem] {
        if searchText.isEmpty {
            return workflowStore.workflows
        }
        return workflowStore.workflows.filter { workflow in
            workflow.name.localizedCaseInsensitiveContains(searchText) ||
            (workflow.description ?? "").localizedCaseInsensitiveContains(searchText)
        }
    }

    private func loadWorkflows() async {
        isLoading = true
        defer { isLoading = false }
        await workflowStore.loadWorkflows()
    }

    private func createWorkflow(name: String, description: String) async {
        do {
            let workflowDef = WorkflowDefinition(
                name: name,
                description: description,
                nodes: [],
                edges: []
            )
            let newWorkflow = try await workflowStore.saveWorkflow(workflowDef)
            selectedWorkflowId = newWorkflow.id
            logger.info("Created workflow: \(newWorkflow.name)")
        } catch {
            logger.error("Failed to create workflow: \(String(describing: error))")
        }
    }

    private func openWorkflow(_ workflow: WorkflowSidebarItem) {
        // Use callback instead of NotificationCenter (SwiftUI best practice)
        onOpenWorkflow?(workflow)
    }

    private func confirmDelete(_ workflow: WorkflowSidebarItem) {
        workflowToDelete = workflow
        showDeleteConfirmation = true
    }

    private func deleteWorkflow(_ workflow: WorkflowSidebarItem) async {
        do {
            try await workflowStore.deleteWorkflow(workflow.id)
            if selectedWorkflowId == workflow.id {
                selectedWorkflowId = nil
            }
            workflowToDelete = nil
            logger.info("Deleted workflow: \(workflow.name)")
        } catch {
            logger.error("Failed to delete workflow: \(String(describing: error))")
        }
    }

    private func duplicateWorkflow(_ workflow: WorkflowSidebarItem) {
        Task {
            do {
                let duplicate = try await workflowStore.duplicateWorkflow(workflow.id)
                selectedWorkflowId = duplicate.id
                logger.info("Duplicated workflow: \(workflow.name)")
            } catch {
                logger.error("Failed to duplicate workflow: \(String(describing: error))")
            }
        }
    }

    private func executeWorkflow(_ workflow: WorkflowSidebarItem) {
        // Execution is handled by WorkflowDetailView which has direct access to workflowStore
        logger.info("Execute requested for workflow: \(workflow.name)")
    }

    private func importWorkflow() {
        isImporting = true
        Task {
            if let importedId = await WorkflowExporter.importFromFile(using: workflowServiceGenerated) {
                await loadWorkflows()
                selectedWorkflowId = importedId
            }
            isImporting = false
        }
    }

    private func exportWorkflow(_ workflow: WorkflowSidebarItem) {
        Task {
            await WorkflowExporter.exportToFile(
                workflow.id,
                name: workflow.name,
                using: workflowServiceGenerated
            )
        }
    }
}

/// Row displaying a workflow in the library list
struct WorkflowLibraryRow: View {
    let workflow: WorkflowSidebarItem

    var body: some View {
        HStack {
            Image(systemName: "flowchart")
                .font(.title2)
                .foregroundColor(.accentColor)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                Text(workflow.name)
                    .font(.headline)

                if let desc = workflow.description, !desc.isEmpty {
                    Text(desc)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }

                HStack(spacing: 8) {
                    Label("\(workflow.nodeCount) nodes", systemImage: "square.on.circle")
                    Label("\(workflow.edgeCount) connections", systemImage: "arrow.right")
                }
                .font(.caption2)
                .foregroundColor(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 4)
    }
}

/// Thumbnail view for workflow grid/icon mode
/// Shows a mini preview of the workflow structure
struct WorkflowThumbnailView: View {
    let workflow: WorkflowSidebarItem
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 8) {
            // Mini workflow preview (visual representation of nodes/edges)
            WorkflowMiniPreview(nodeCount: workflow.nodeCount, edgeCount: workflow.edgeCount)
                .frame(width: 120, height: 80)
                .background(Color(.controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
                )

            // Workflow name
            Text(workflow.name)
                .font(.caption)
                .fontWeight(.medium)
                .lineLimit(2)
                .multilineTextAlignment(.center)
                .frame(width: 120)

            // Stats
            HStack(spacing: 4) {
                Image(systemName: "square.on.circle")
                Text("\(workflow.nodeCount)")
                Image(systemName: "arrow.right")
                Text("\(workflow.edgeCount)")
            }
            .font(.caption2)
            .foregroundColor(.secondary)
        }
        .padding(8)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

/// Mini preview showing a schematic representation of the workflow
struct WorkflowMiniPreview: View {
    let nodeCount: Int
    let edgeCount: Int

    var body: some View {
        GeometryReader { geometry in
            Canvas { context, size in
                let nodeRadius: CGFloat = 6
                let centerX = size.width / 2
                let centerY = size.height / 2

                // Draw placeholder nodes in a simple layout
                let displayNodes = min(nodeCount, 5)  // Max 5 nodes in preview
                let nodePositions = calculateNodePositions(
                    count: displayNodes,
                    in: CGRect(origin: .zero, size: size),
                    nodeRadius: nodeRadius
                )

                // Draw edges (simple lines between consecutive nodes)
                if displayNodes > 1 {
                    for idx in 0..<(displayNodes - 1) {
                        let start = nodePositions[idx]
                        let end = nodePositions[idx + 1]
                        var path = Path()
                        path.move(to: start)
                        path.addLine(to: end)
                        context.stroke(path, with: .color(.secondary.opacity(0.5)), lineWidth: 1)
                    }
                }

                // Draw nodes
                for position in nodePositions {
                    let rect = CGRect(
                        x: position.x - nodeRadius,
                        y: position.y - nodeRadius,
                        width: nodeRadius * 2,
                        height: nodeRadius * 2
                    )
                    context.fill(
                        Path(ellipseIn: rect),
                        with: .color(.accentColor)
                    )
                }

                // If no nodes, show placeholder
                if nodeCount == 0 {
                    let rect = CGRect(
                        x: centerX - 20,
                        y: centerY - 10,
                        width: 40,
                        height: 20
                    )
                    context.stroke(
                        Path(roundedRect: rect, cornerRadius: 4),
                        with: .color(.secondary.opacity(0.3)),
                        style: StrokeStyle(lineWidth: 1, dash: [4, 2])
                    )
                }
            }
        }
    }

    private func calculateNodePositions(count: Int, in rect: CGRect, nodeRadius: CGFloat) -> [CGPoint] {
        guard count > 0 else { return [] }

        let padding: CGFloat = nodeRadius + 4
        let availableWidth = rect.width - padding * 2
        let availableHeight = rect.height - padding * 2

        if count == 1 {
            return [CGPoint(x: rect.midX, y: rect.midY)]
        }

        // Arrange nodes in a simple left-to-right, top-to-bottom grid
        var positions: [CGPoint] = []
        let cols = min(count, 3)
        let rows = Int(ceil(Double(count) / Double(cols)))

        let xSpacing = availableWidth / CGFloat(max(cols - 1, 1))
        let ySpacing = availableHeight / CGFloat(max(rows - 1, 1))

        for idx in 0..<count {
            let col = idx % cols
            let row = idx / cols
            let positionX = padding + CGFloat(col) * xSpacing
            let positionY = padding + CGFloat(row) * ySpacing
            positions.append(CGPoint(x: positionX, y: positionY))
        }

        return positions
    }
}

/// Detail view for a selected workflow
struct WorkflowDetailView: View {
    let workflow: WorkflowSidebarItem
    let onEdit: () -> Void
    let onDelete: () -> Void
    let onDuplicate: () -> Void
    let onExecute: () -> Void
    let onExport: () -> Void

    @EnvironmentObject var workflowStore: WorkflowStore
    @State private var isExecuting = false
    @State private var executionStatus: String?
    @State private var executionError: String?
    @State private var currentThreadId: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack {
                    Image(systemName: "flowchart")
                        .font(.system(size: 48))
                        .foregroundColor(.accentColor)

                    VStack(alignment: .leading) {
                        Text(workflow.name)
                            .font(.largeTitle)
                            .fontWeight(.bold)

                        if let desc = workflow.description, !desc.isEmpty {
                            Text(desc)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()
                }

                Divider()

                // Stats
                HStack(spacing: 32) {
                    StatView(title: "Nodes", value: "\(workflow.nodeCount)", icon: "square.on.circle")
                    StatView(title: "Connections", value: "\(workflow.edgeCount)", icon: "arrow.right")
                }

                Divider()

                // Execution section
                VStack(alignment: .leading, spacing: 12) {
                    Text("Execute")
                        .font(.headline)

                    HStack(spacing: 12) {
                        Button {
                            executeWorkflow()
                        } label: {
                            Label(isExecuting ? "Running..." : "Run Workflow", systemImage: "play.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .disabled(isExecuting || workflow.nodeCount == 0)
                    }

                    if let status = executionStatus {
                        HStack {
                            if isExecuting {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                            }
                            Text(status)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(8)
                        .background(Color(.controlBackgroundColor))
                        .cornerRadius(6)
                    }

                    if let error = executionError {
                        HStack {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(8)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(6)
                    }
                }

                Divider()

                // Actions
                VStack(alignment: .leading, spacing: 12) {
                    Text("Actions")
                        .font(.headline)

                    HStack(spacing: 12) {
                        Button {
                            onEdit()
                        } label: {
                            Label("Edit Workflow", systemImage: "pencil")
                        }
                        .buttonStyle(.borderedProminent)

                        Button {
                            onDuplicate()
                        } label: {
                            Label("Duplicate", systemImage: "doc.on.doc")
                        }
                        .buttonStyle(.bordered)

                        Button {
                            onExport()
                        } label: {
                            Label("Export", systemImage: "square.and.arrow.up")
                        }
                        .buttonStyle(.bordered)

                        Button(role: .destructive) {
                            onDelete()
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .buttonStyle(.bordered)
                    }
                }

                Spacer()
            }
            .padding(24)
        }
    }

    // MARK: - Actions

    private func executeWorkflow() {
        Task {
            isExecuting = true
            executionStatus = "Starting workflow..."
            executionError = nil

            do {
                let thread = try await workflowStore.executeWorkflow(workflow.id)
                currentThreadId = thread.threadId
                executionStatus = "Thread: \(thread.threadId) - \(thread.status.rawValue)"

                // Poll for completion
                await pollForCompletion(threadId: thread.threadId)
            } catch {
                executionError = error.localizedDescription
                executionStatus = nil
                isExecuting = false
            }
        }
    }

    private func pollForCompletion(threadId: String) async {
        // Poll every 2 seconds for status updates
        while isExecuting {
            do {
                try await Task.sleep(nanoseconds: 2_000_000_000)
                guard !Task.isCancelled else { break }

                let status = try await workflowStore.getExecutionStatus(threadId)
                executionStatus = "Thread: \(status.threadId) - \(status.status.rawValue)"

                switch status.status {
                case .completed:
                    isExecuting = false
                    executionStatus = "Completed successfully"
                case .failed:
                    isExecuting = false
                    executionError = status.error ?? "Workflow failed"
                    executionStatus = nil
                case .paused:
                    executionStatus = "Paused - waiting for input"
                case .running:
                    // Continue polling
                    break
                }
            } catch {
                // Stop polling on error
                isExecuting = false
                executionError = "Failed to check status: \(error.localizedDescription)"
            }
        }
    }
}

/// Simple stat display view
struct StatView: View {
    let title: String
    let value: String
    let icon: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(.secondary)
            Text(value)
                .font(.title)
                .fontWeight(.bold)
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}

/// Sheet for creating a new workflow
struct NewWorkflowSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var description = ""
    let onCreate: (String, String) async -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Workflow Details") {
                    TextField("Name", text: $name)
                    TextField("Description", text: $description)
                }
            }
            .navigationTitle("New Workflow")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            await onCreate(name, description)
                            dismiss()
                        }
                    }
                    .disabled(name.isEmpty)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 200)
    }
}

#Preview {
    let ficheroClient = FicheroClient(libraryPath: "/tmp/preview.fichero")
    return WorkflowLibraryView(displayMode: .list)
        .environmentObject(WorkflowStore(ficheroClient: ficheroClient))
        .environmentObject(WorkflowServiceGenerated(ficheroClient: ficheroClient))
}
