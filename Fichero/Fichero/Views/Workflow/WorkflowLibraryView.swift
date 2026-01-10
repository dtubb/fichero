import SwiftUI
import OSLog

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
                WorkflowListView(onOpenWorkflow: onOpenWorkflow)
            case .chains:
                WorkflowChainListView(apiClient: apiClient)
            }
        }
    }
}

/// View for browsing and managing saved workflows
struct WorkflowListView: View {
    @EnvironmentObject var workflowStore: WorkflowStore
    @State private var searchText = ""
    @State private var selectedWorkflowId: String?
    @State private var showNewWorkflowSheet = false
    @State private var showDeleteConfirmation = false
    @State private var workflowToDelete: WorkflowSidebarItem?
    @State private var isLoading = false

    /// Callback when user wants to open a workflow in the editor
    var onOpenWorkflow: ((WorkflowSidebarItem) -> Void)?

    var body: some View {
        NavigationSplitView {
            workflowList
        } detail: {
            if let selectedId = selectedWorkflowId,
               let workflow = workflowStore.workflows.first(where: { $0.id == selectedId }) {
                WorkflowDetailView(
                    workflow: workflow,
                    onEdit: { openWorkflow(workflow) },
                    onDelete: { confirmDelete(workflow) },
                    onDuplicate: { duplicateWorkflow(workflow) },
                    onExecute: { executeWorkflow(workflow) }
                )
            } else {
                ContentUnavailableView(
                    "No Workflow Selected",
                    systemImage: "flowchart",
                    description: Text("Select a workflow to view its details")
                )
            }
        }
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

    @ViewBuilder
    private var workflowList: some View {
        Group {
            if isLoading && workflowStore.workflows.isEmpty {
                ProgressView("Loading workflows...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredWorkflows.isEmpty {
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
            } else {
                List(filteredWorkflows, selection: $selectedWorkflowId) { workflow in
                    WorkflowLibraryRow(workflow: workflow)
                        .tag(workflow.id)
                        .contextMenu {
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

                            Divider()

                            Button(role: .destructive) {
                                confirmDelete(workflow)
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            }
        }
        .navigationTitle("Workflow Library")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showNewWorkflowSheet = true
                } label: {
                    Image(systemName: "plus")
                }
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await loadWorkflows() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(isLoading)
            }
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

/// Detail view for a selected workflow
struct WorkflowDetailView: View {
    let workflow: WorkflowSidebarItem
    let onEdit: () -> Void
    let onDelete: () -> Void
    let onDuplicate: () -> Void
    let onExecute: () -> Void

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
    WorkflowLibraryView()
        .environmentObject(WorkflowStore(apiClient: APIClient()))
        .environmentObject(APIClient())
}
