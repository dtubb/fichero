import SwiftUI
import OSLog
import FicheroAPIClient

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowLibraryView")

/// Tab selection for workflow library
enum WorkflowLibraryTab: String, CaseIterable {
    case workflows = "Workflows"
    case chains = "Chains"
}

// View for browsing and managing saved workflows and workflow chains
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

// View for browsing and managing saved workflows
// swiftlint:disable:next type_body_length
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
        .onChange(of: tableSortOrder) { _, _ in
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

// Components extracted to WorkflowLibraryView/ subfolder:
// - WorkflowLibraryRow.swift
// - WorkflowThumbnailView.swift
// - WorkflowMiniPreview.swift
// - WorkflowDetailView.swift (includes StatView)
// - NewWorkflowSheet.swift

#Preview {
    let ficheroClient = FicheroClient(libraryPath: "/tmp/preview.fichero")
    return WorkflowLibraryView(displayMode: .list)
        .environmentObject(WorkflowStore(ficheroClient: ficheroClient))
        .environmentObject(WorkflowServiceGenerated(ficheroClient: ficheroClient))
}
