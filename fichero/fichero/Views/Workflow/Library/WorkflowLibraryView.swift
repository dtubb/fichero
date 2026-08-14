import FicheroAPIClient
import SwiftUI

// WorkflowLibraryView + its tab enum deleted (views audit 2026-08-10:
// an unreachable second workflow-list shell; Daniel: the mode-shell era is over).
// WorkflowListView below remains the live list renderer.

struct WorkflowListView: View {
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(WorkflowService.self) var workflowService
    @State var searchText = ""
    @State var selectedWorkflowId: String?
    @State var selectedWorkflowIds: Set<String> = []
    @State var showNewWorkflowSheet = false
    @State var showDeleteConfirmation = false
    @State var workflowsToDelete: [WorkflowSidebarItem] = []
    @State var isLoading = false
    @State var tableSortOrder = [KeyPathComparator(\WorkflowSidebarItem.name)]
    @State var isImporting = false
    @State var isManagingDefaults = false
    @State private var showResetDefaultsConfirmation = false
    @State var templateOperationMessage: String?
    @State var workflowToRename: WorkflowSidebarItem?
    @State var renameDraft: String = ""
    let featureManager = FeatureManager.shared
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
                    Text(
                        "Are you sure you want to delete \(workflowsToDelete.count) workflows? "
                            + "This action cannot be undone."
                    )
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
                case .columns, .grid, .cards, .timeline, .calendar, .geoMap, .canvas, .space, .workspace:
                    // Columns/Canvas/Space fall back to the same list view for
                    // workflows — the Miller browser is a library-content
                    // affordance (#4160 step 4), not a workflow one.
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
                .accessibilityLabel("Create new workflow")

                // #930 — collapsed Install + Reset into one Reset
                // action. Reset is a superset of Install (ensures all
                // defaults are present AND replaces any that the user
                // has edited), so the separate Install button was
                // redundant + confusing ("Not sure install defaults
                // does anything" — the user). Confirmation dialog warns
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
                    .accessibilityLabel("Import workflow from JSON file")
                }

                Button(role: .destructive) {
                    promptDeleteSelected()
                } label: {
                    Image(systemName: "trash")
                }
                .disabled(currentDeletionSelection.isEmpty)
                .help("Delete selection")
                .accessibilityLabel("Delete selected workflows")
            }
        }
        #if os(macOS)
        .onDeleteCommand(perform: promptDeleteSelected)
        #endif
    }
}

// Components extracted to WorkflowLibraryView/ subfolder:
// - WorkflowLibraryRow.swift
// - WorkflowThumbnailView.swift
// - WorkflowMiniPreview.swift
// - WorkflowDetailView.swift (includes StatView)
// - NewWorkflowSheet.swift
