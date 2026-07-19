import SwiftUI

// Display-mode subviews (icon grid, list, table), empty state, and the
// shared context menu for WorkflowListView. Split out of WorkflowLibraryView
// to keep the type body under the SwiftLint threshold.
extension WorkflowListView {
    // MARK: - Icon Grid View

    var iconGridView: some View {
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

    var listView: some View {
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
    func workflowRow(_ workflow: WorkflowSidebarItem) -> some View {
        WorkflowLibraryRow(workflow: workflow)
            .tag(workflow.id)
            .contentShape(Rectangle())
            // Single click opens the workflow in the node editor (#3918). A
            // simultaneousGesture runs ALONGSIDE List(selection:) rather than
            // replacing it, so click/keyboard selection, multi-select, and the
            // context menu are all preserved — an exclusive .onTapGesture (the old
            // count:2 double-click) fights the list's own selection recognizer.
            // Keyboard arrow navigation changes selection without firing this
            // mouse tap, so it never opens on mere navigation; right-click opens
            // the context menu, not the workflow.
            .simultaneousGesture(TapGesture().onEnded {
                openWorkflow(workflow)
            })
            .contextMenu {
                workflowContextMenu(for: workflow)
            }
    }

    func folderSectionLabel(_ path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }

    // MARK: - Table View

    var tableView: some View {
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

    var emptyStateView: some View {
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
    func workflowContextMenu(for workflow: WorkflowSidebarItem) -> some View {
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

    var filteredWorkflows: [WorkflowSidebarItem] {
        if searchText.isEmpty {
            return workflowStore.workflows
        }
        return workflowStore.workflows.filter { workflow in
            workflow.name.localizedCaseInsensitiveContains(searchText) ||
                (workflow.description ?? "").localizedCaseInsensitiveContains(searchText)
        }
    }
}
