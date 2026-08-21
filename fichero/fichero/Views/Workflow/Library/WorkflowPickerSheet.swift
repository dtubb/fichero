import SwiftUI

/// Sheet for picking a workflow to run on selected documents
struct WorkflowPickerSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(WindowState.self) private var windowState

    let selectedDocumentIds: [String]
    let onSelect: (String) -> Void

    @State private var searchText = ""

    private var workflows: [WorkflowSidebarItem] {
        let library = libraryManager.getLibrary(id: windowState.libraryId) ?? libraryManager.globalLibrary
        let own = library?.workflowStore.directlyRunnableWorkflows ?? []
        if !own.isEmpty { return own }
        // GLOBAL fallback (user, 2026-08-20: "No workflows available" on a
        // non-global library): a store that loaded during the engine's boot
        // window (401) stays empty, and defaults are global by design
        // (#4450) — the engine resolves default ids against the global
        // library on run. Same fallback the sidebar menu already uses.
        return libraryManager.globalLibrary?.workflowStore.directlyRunnableWorkflows ?? []
    }

    /// The store this sheet reads — retried on appear when empty, so a load
    /// that failed during engine boot heals the moment the picker opens.
    private var pickerWorkflowStore: WorkflowStore? {
        (libraryManager.getLibrary(id: windowState.libraryId)
            ?? libraryManager.globalLibrary)?.workflowStore
    }

    private var filteredWorkflows: [WorkflowSidebarItem] {
        if searchText.isEmpty {
            return workflows
        }
        return workflows.filter { workflow in
            workflow.name.localizedCaseInsensitiveContains(searchText) ||
                (workflow.description?.localizedCaseInsensitiveContains(searchText) ?? false)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            VStack(spacing: 8) {
                Text("Run Workflow")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Select a workflow to run on \(selectedDocumentIds.count) documents")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding()

            Divider()

            // Search bar
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search workflows", text: $searchText)
                    .textFieldStyle(.plain)

                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear workflow search")
                }
            }
            .padding()
            .background(Color(platformColor: .controlBackgroundColor))

            Divider()

            // Workflow list
            if filteredWorkflows.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: searchText.isEmpty ? "flowchart" : "magnifyingglass")
                        .font(.system(size: 48))
                        .foregroundStyle(.secondary)
                    Text(searchText.isEmpty ? "No workflows available" : "No workflows found")
                        .font(.headline)
                        .foregroundStyle(.secondary)
                    if searchText.isEmpty {
                        Text("Create a workflow first to run batches")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(filteredWorkflows) { workflow in
                    Button {
                        onSelect(workflow.id)
                        dismiss()
                    } label: {
                        WorkflowPickerRow(workflow: workflow)
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.plain)
            }

            Divider()

            // Footer
            HStack {
                Spacer()
                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)
            }
            .padding()
        }
        // macOS sheets need an explicit size; on iPhone a fixed 500pt width
        // overflows the ~390pt screen, so let iOS use natural sheet sizing (#3666).
        #if os(macOS)
        .frame(width: 500, height: 600)
        // Heal a boot-window load failure the moment the picker opens
        // (user, 2026-08-20: "No workflows available").
        .task {
            if workflows.isEmpty {
                await pickerWorkflowStore?.loadWorkflows()
                if workflows.isEmpty {
                    await libraryManager.globalLibrary?.workflowStore.loadWorkflows()
                }
            }
        }
        #endif
    }
}

/// Row in the workflow picker list
private struct WorkflowPickerRow: View {
    let workflow: WorkflowSidebarItem

    var body: some View {
        HStack(spacing: 12) {
            // Icon
            Image(systemName: "flowchart")
                .font(.title3)
                .foregroundStyle(.blue)
                .frame(width: 32)

            // Content
            VStack(alignment: .leading, spacing: 4) {
                Text(workflow.name)
                    .font(.body)
                    .foregroundStyle(.primary)

                if let description = workflow.description, !description.isEmpty {
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                // Stats
                HStack(spacing: 12) {
                    Label("\(workflow.nodeCount) nodes", systemImage: "circle.grid.3x3")
                    if workflow.edgeCount > 0 {
                        Label("\(workflow.edgeCount) edges", systemImage: "arrow.right")
                    }
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }

            Spacer()

            // Chevron
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }
}

#Preview {
    WorkflowPickerSheet(
        selectedDocumentIds: ["doc1", "doc2", "doc3"],
        onSelect: { workflowId in
            print("Selected workflow: \(workflowId)")
        }
    )
    .environment(LibraryManager.shared)
    .environment(WindowState(libraryId: LibraryManager.globalLibraryId))
}
