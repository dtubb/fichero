import FicheroAPIClient
import OSLog
import SwiftUI
// swiftlint:disable file_length

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowLibraryView")

/// Tab selection for workflow library
enum WorkflowLibraryTab: String, CaseIterable {
    case workflows = "Workflows"
    case chains = "Chains"
}

// View for browsing and managing saved workflows and workflow chains
struct WorkflowLibraryView: View {
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(APIClient.self) var apiClient
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
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(WorkflowServiceGenerated.self) var workflowServiceGenerated
    @State private var searchText = ""
    @State private var selectedWorkflowId: String?
    @State private var selectedWorkflowIds: Set<String> = []
    @State private var showNewWorkflowSheet = false
    @State private var showDeleteConfirmation = false
    @State private var workflowsToDelete: [WorkflowSidebarItem] = []
    @State private var isLoading = false
    @State private var tableSortOrder = [KeyPathComparator(\WorkflowSidebarItem.name)]
    @State private var isImporting = false
    @State private var isManagingDefaults = false
    @State private var showResetDefaultsConfirmation = false
    @State private var templateOperationMessage: String?
    @State private var workflowToRename: WorkflowSidebarItem?
    @State private var renameDraft: String = ""
    @ObservedObject var featureManager = FeatureManager.shared
    /// Canonical "a run changed things" staleness tick — drives auto-refresh
    /// in place of the removed manual Refresh button (#1022).
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    /// View display mode from toolbar
    let displayMode: ViewDisplayMode

    /// Callback when user wants to open a workflow in the editor
    var onOpenWorkflow: ((WorkflowSidebarItem) -> Void)?

    var body: some View {
        workflowContent
            // No per-view toolbar search: the toolbar search is global and
            // always searches files/documents (ContentView owns the single
            // .searchable). A second .searchable here is a duplicate
            // com.apple.SwiftUI.search on the same NSToolbar and crashes at
            // launch (#3163). The list shows all workflows.
            .task {
                guard !Task.isCancelled else { return }
                await loadWorkflows()
            }
            .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
                Task { await loadWorkflows() }
            }
            .sheet(isPresented: $showNewWorkflowSheet) {
                NewWorkflowSheet { name, description in
                    await createWorkflow(name: name, description: description)
                }
                .environment(executionObserver)
            }
            .alert("Delete Workflow?", isPresented: $showDeleteConfirmation) {
                Button("Cancel", role: .cancel) {
                    workflowsToDelete = []
                }
                Button("Delete", role: .destructive) {
                    let workflows = workflowsToDelete
                    if !workflows.isEmpty {
                        Task { await deleteWorkflows(workflows) }
                    }
                }
            } message: {
                if workflowsToDelete.count == 1, let workflow = workflowsToDelete.first {
                    Text("Are you sure you want to delete \"\(workflow.name)\"? This action cannot be undone.")
                } else if !workflowsToDelete.isEmpty {
                    Text("Are you sure you want to delete \(workflowsToDelete.count) workflows? This action cannot be undone.")
                }
            }
            .alert(
                "Rename Workflow",
                isPresented: Binding(
                    get: { workflowToRename != nil },
                    set: { show in if !show { workflowToRename = nil } }
                ),
                presenting: workflowToRename
            ) { workflow in
                TextField("Name", text: $renameDraft)
                Button("Cancel", role: .cancel) {}
                Button("Rename") {
                    let newName = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !newName.isEmpty, newName != workflow.name else { return }
                    Task {
                        do {
                            _ = try await workflowStore.renameWorkflow(workflow.id, to: newName)
                            await workflowStore.loadWorkflows()
                        } catch {
                            templateOperationMessage = "Rename failed: \(error.localizedDescription)"
                        }
                    }
                }
            } message: { workflow in
                Text("Enter a new name for \"\(workflow.name)\".")
            }
            .alert("Reset Default Workflows?", isPresented: $showResetDefaultsConfirmation) {
                Button("Cancel", role: .cancel) {}
                Button("Reset", role: .destructive) {
                    Task { await resetDefaultWorkflows() }
                }
            } message: {
                Text("This removes and recreates built-in default workflows.")
            }
            .alert(
                "Workflow Templates",
                isPresented: Binding(
                    get: { templateOperationMessage != nil },
                    set: { show in
                        if !show {
                            templateOperationMessage = nil
                        }
                    }
                )
            ) {
                Button("OK") { templateOperationMessage = nil }
            } message: {
                Text(templateOperationMessage ?? "")
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
                case .canvas, .space, .workspace:
                    // Canvas/Space fall back to the same list view for workflows
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

                // #930 — collapsed Install + Reset into one Reset
                // action. Reset is a superset of Install (ensures all
                // defaults are present AND replaces any that the user
                // has edited), so the separate Install button was
                // redundant + confusing ("Not sure install defaults
                // does anything" — Daniel). Confirmation dialog warns
                // about overwriting user edits before firing.
                Button(role: .destructive) {
                    showResetDefaultsConfirmation = true
                } label: {
                    Label("Reset Default Workflows", systemImage: "sparkles")
                }
                .disabled(isManagingDefaults)
                .help("Reinstall the built-in default workflows from scratch (overwrites any edits to defaults)")

                if featureManager.isWorkflowImportExportEnabled {
                    Button {
                        importWorkflow()
                    } label: {
                        Image(systemName: "square.and.arrow.down")
                    }
                    .disabled(isImporting)
                    .help("Import workflow from JSON file")
                }

                Button(role: .destructive) {
                    promptDeleteSelected()
                } label: {
                    Image(systemName: "trash")
                }
                .disabled(currentDeletionSelection.isEmpty)
                .help("Delete selection")
            }
        }
        #if os(macOS)
        .onDeleteCommand(perform: promptDeleteSelected)
        #endif
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
        // Group by folder_path so default templates seeded under /Catalogue
        // and /Transcribe surface as section headers in the Library list,
        // matching the Run Workflow context menu grouping (#722 / #724).
        // Top-level workflows render first without a header; folder buckets
        // follow alphabetically. Section beats DisclosureGroup inside List —
        // see MEMORY feedback_disclosure_group_custom_style.md.
        let grouped = Dictionary(grouping: filteredWorkflows) { workflow in
            workflow.folderPath.isEmpty ? "/" : workflow.folderPath
        }
        let topLevel = (grouped["/"] ?? []).sorted { $0.name < $1.name }
        let folderKeys = grouped.keys.filter { $0 != "/" }.sorted()

        return List(selection: $selectedWorkflowIds) {
            if !topLevel.isEmpty {
                ForEach(topLevel) { workflow in
                    workflowRow(workflow)
                }
            }
            ForEach(folderKeys, id: \.self) { folderPath in
                let inFolder = (grouped[folderPath] ?? []).sorted { $0.name < $1.name }
                Section {
                    ForEach(inFolder) { workflow in
                        workflowRow(workflow)
                    }
                } header: {
                    Text(folderSectionLabel(folderPath))
                        .foregroundStyle(.primary)
                }
            }
        }
        .onChange(of: selectedWorkflowIds) { _, newValue in
            selectedWorkflowId = newValue.first
        }
    }

    @ViewBuilder
    private func workflowRow(_ workflow: WorkflowSidebarItem) -> some View {
        WorkflowLibraryRow(workflow: workflow)
            .tag(workflow.id)
            .contentShape(Rectangle())
            .onTapGesture(count: 2) {
                openWorkflow(workflow)
            }
            .contextMenu {
                workflowContextMenu(for: workflow)
            }
    }

    private func folderSectionLabel(_ path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }

    // MARK: - Table View

    private var tableView: some View {
        Table(filteredWorkflows, selection: $selectedWorkflowIds, sortOrder: $tableSortOrder) {
            TableColumn("Name", value: \.name) { workflow in
                HStack {
                    Image(systemName: "flowchart")
                        .foregroundColor(.accentColor)
                    Text(workflow.displayName)
                    if workflow.isSystem {
                        Image(systemName: "lock.fill")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
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
        if workflow.isSystem {
            Button {
                duplicateWorkflow(workflow)
            } label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            }
        } else {
            Button {
                openWorkflow(workflow)
            } label: {
                Label("Edit", systemImage: "pencil")
            }

            Button {
                renameDraft = workflow.name
                workflowToRename = workflow
            } label: {
                Label("Rename…", systemImage: "character.cursor.ibeam")
            }

            Button {
                duplicateWorkflow(workflow)
            } label: {
                Label("Duplicate", systemImage: "doc.on.doc")
            }

            if featureManager.isWorkflowImportExportEnabled {
                Button {
                    exportWorkflow(workflow)
                } label: {
                    Label("Export to JSON...", systemImage: "square.and.arrow.up")
                }
            }

            Divider()

            Button(role: .destructive) {
                confirmDelete(deleteSelection(containing: workflow))
            } label: {
                Label("Delete", systemImage: "trash")
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
        confirmDelete([workflow])
    }

    private func confirmDelete(_ workflows: [WorkflowSidebarItem]) {
        workflowsToDelete = workflows
        showDeleteConfirmation = !workflows.isEmpty
    }

    private func deleteSelection(containing workflow: WorkflowSidebarItem? = nil) -> [WorkflowSidebarItem] {
        let selection = currentDeletionSelection
        guard let workflow else { return selection }
        if selection.contains(where: { $0.id == workflow.id }) {
            return selection
        }
        return [workflow]
    }

    private var currentDeletionSelection: [WorkflowSidebarItem] {
        var selectedIds = selectedWorkflowIds
        if let selectedWorkflowId {
            selectedIds.insert(selectedWorkflowId)
        }
        guard !selectedIds.isEmpty else { return [] }
        return workflowStore.workflows.filter { workflow in
            selectedIds.contains(workflow.id) && !workflow.isSystem
        }
    }

    private func promptDeleteSelected() {
        confirmDelete(currentDeletionSelection)
    }

    private func deleteWorkflows(_ workflows: [WorkflowSidebarItem]) async {
        do {
            for workflow in workflows {
                try await workflowStore.deleteWorkflow(workflow.id)
            }
            let deletedIds = Set(workflows.map(\.id))
            selectedWorkflowIds.subtract(deletedIds)
            selectedWorkflowId = selectedWorkflowIds.first
            workflowsToDelete = []
            logger.info("Deleted \(workflows.count, privacy: .public) workflow(s)")
        } catch {
            logger.error("Failed to delete workflows: \(String(describing: error))")
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
            do {
                if let importedId = try await WorkflowExporter.importFromFile(using: workflowServiceGenerated) {
                    await loadWorkflows()
                    selectedWorkflowId = importedId
                }
            } catch {
                logger.error("Failed to import workflow: \(error.localizedDescription)")
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

    // installDefaultWorkflows() removed at #930 fix — Reset is a
    // superset (adds missing AND replaces user-edited) so the
    // separate Install action was redundant + confusing.

    private func resetDefaultWorkflows() async {
        guard !isManagingDefaults else { return }
        isManagingDefaults = true
        defer { isManagingDefaults = false }

        do {
            let created = try await workflowStore.resetDefaultWorkflowTemplates()
            templateOperationMessage = created.isEmpty
                ? "Default workflows are already up to date."
                : "Reinstalled \(created.count) default workflow\(created.count == 1 ? "" : "s")."
        } catch {
            templateOperationMessage = "Failed to reset defaults: \(error.localizedDescription)"
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
        .environment(WorkflowStore(ficheroClient: ficheroClient))
        .environment(WorkflowServiceGenerated(ficheroClient: ficheroClient))
}
