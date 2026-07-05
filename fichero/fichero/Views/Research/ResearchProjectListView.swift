import SwiftUI

struct ResearchProjectListView: View {
    @Environment(ResearchService.self) var researchService
    @Environment(DocumentStore.self) var documentStore: DocumentStore

    @State private var showingNewProject = false
    @State private var newProjectName = ""
    @State private var projectsToDelete: [ResearchProject] = []
    @State private var showingDeleteConfirm = false
    @State private var showingNewWorkspace = false
    @State private var newWorkspaceName = ""
    @State private var selectedProjectIds: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            Spacer().frame(height: 12)
            projectList
            Divider()
            workspacesSection
            Divider()
            bottomToolbar
        }
        // Load existing projects + workspaces when the Research surface appears.
        // Without this the lists were always empty and previously-created items
        // were invisible — which read as "can't add" (#1614, #1617).
        .task {
            await researchService.loadProjects()
            await documentStore.loadWorkspaces()
        }
    }

    // MARK: - Workspaces section (#1617)

    private var workspacesSection: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Workspaces")
                .font(.caption)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 12)
                .padding(.top, 6)

            if documentStore.workspaces.isEmpty {
                Text("No workspaces yet — create one below.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .padding(.horizontal, 12)
                    .padding(.bottom, 6)
            } else {
                ForEach(documentStore.workspaces) { workspace in
                    workspaceRow(workspace)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func workspaceRow(_ workspace: Document) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "square.stack.3d.up.fill")
                .foregroundStyle(.purple)
            Text(workspace.name)
                .font(.body)
            Spacer()
            if !workspace.curatedItems.isEmpty {
                Text("\(workspace.curatedItems.count)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var projectList: some View {
        if researchService.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if researchService.projects.isEmpty {
            ContentUnavailableView {
                Label("No Projects", systemImage: "flask")
            } description: {
                Text("Create a research project to get started.")
            } actions: {
                Button("New Project") { showingNewProject = true }
                    .buttonStyle(.borderedProminent)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(selection: $selectedProjectIds) {
                Section("Research") {
                    ForEach(researchService.projects) { project in
                        projectRow(project)
                    }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
            .background(Color(platformColor: .windowBackgroundColor))
            .onChange(of: selectedProjectIds) { _, newValue in
                researchService.selectedProjectId = newValue.first
            }
            .onChange(of: researchService.selectedProjectId) { _, newValue in
                if let newValue {
                    selectedProjectIds = [newValue]
                } else {
                    selectedProjectIds.removeAll()
                }
            }
            #if os(macOS)
            .onDeleteCommand(perform: confirmDeleteSelection)
            #endif
        }
    }

    private func projectRow(_ project: ResearchProject) -> some View {
        Label {
            VStack(alignment: .leading, spacing: 2) {
                Text(project.name)
                    .font(.body)
                    .foregroundStyle(.primary)
                if !project.description.isEmpty {
                    Text(project.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        } icon: {
            Image(systemName: statusIcon(project.status))
                .foregroundStyle(statusColor(project.status))
        }
        .tag(project.id)
        .contextMenu {
            Button("Delete Project", role: .destructive) {
                if selectedProjectIds.contains(project.id) {
                    confirmDeleteSelection()
                } else {
                    confirmDelete([project])
                }
            }
        }
    }

    private func confirmDeleteSelection() {
        let projects = researchService.projects.filter { selectedProjectIds.contains($0.id) }
        guard !projects.isEmpty else { return }
        confirmDelete(projects)
    }

    private func confirmDelete(_ projects: [ResearchProject]) {
        projectsToDelete = projects
        showingDeleteConfirm = !projects.isEmpty
    }

    private func deleteProjects(_ projects: [ResearchProject]) async {
        for project in projects {
            try? await researchService.deleteProject(id: project.id)
        }
        let deletedIds = Set(projects.map(\.id))
        selectedProjectIds.subtract(deletedIds)
        researchService.selectedProjectId = selectedProjectIds.first
        projectsToDelete = []
        await researchService.loadProjects()
    }

    private var bottomToolbar: some View {
        HStack(spacing: 12) {
            Button {
                showingNewProject = true
            } label: {
                Label("New Project", systemImage: "plus")
            }
            .buttonStyle(.plain)
            .help("New Research Project")

            Button(role: .destructive) {
                confirmDeleteSelection()
            } label: {
                Label("Delete Selection", systemImage: "trash")
            }
            .buttonStyle(.plain)
            .disabled(selectedProjectIds.isEmpty)
            .help("Delete selected research projects")

            Button {
                showingNewWorkspace = true
            } label: {
                Label("New Workspace", systemImage: "square.stack.3d.up.badge.a")
            }
            .buttonStyle(.plain)
            .help("New Workspace")

            Spacer()
        }
        .padding(.horizontal, 12)
        .frame(height: 32)
        .popover(isPresented: $showingNewProject) {
            newProjectForm
        }
        .popover(isPresented: $showingNewWorkspace) {
            newWorkspaceForm
        }
        .confirmationDialog(
            "Delete Project?",
            isPresented: $showingDeleteConfirm
        ) {
            Button("Delete", role: .destructive) {
                let projects = projectsToDelete
                if !projects.isEmpty {
                    Task { await deleteProjects(projects) }
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            if projectsToDelete.count == 1, let project = projectsToDelete.first {
                Text("Are you sure you want to delete \"\(project.name)\"? This action cannot be undone.")
            } else if !projectsToDelete.isEmpty {
                Text("Are you sure you want to delete \(projectsToDelete.count) research projects? This action cannot be undone.")
            }
        }
    }

    private var newProjectForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("New Research Project").font(.headline)
            TextField("Project name", text: $newProjectName)
                .textFieldStyle(.roundedBorder)
                .frame(width: 240)
            HStack {
                Button("Cancel") { showingNewProject = false }
                Button("Create") {
                    let name = newProjectName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !name.isEmpty else { return }
                    Task {
                        do {
                            let project = try await researchService.createProject(name: name)
                            researchService.selectedProjectId = project.id
                        } catch {
                            // Surface the failure instead of silently swallowing it,
                            // so a broken create is visible rather than a no-op (#1614).
                            researchService.error = error.localizedDescription
                        }
                    }
                    newProjectName = ""
                    showingNewProject = false
                }
                .buttonStyle(.borderedProminent)
                .disabled(newProjectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding()
    }

    private var newWorkspaceForm: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("New Workspace").font(.headline)
            TextField("Workspace name", text: $newWorkspaceName)
                .textFieldStyle(.roundedBorder)
                .frame(width: 240)
            HStack {
                Button("Cancel") { showingNewWorkspace = false }
                Button("Create") {
                    let name = newWorkspaceName.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !name.isEmpty else { return }
                    Task {
                        do {
                            _ = try await documentStore.createWorkspace(name: name)
                        } catch {
                            documentStore.error = error
                        }
                    }
                    newWorkspaceName = ""
                    showingNewWorkspace = false
                }
                .buttonStyle(.borderedProminent)
                .disabled(newWorkspaceName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding()
    }

    private func statusIcon(_ status: ResearchProjectStatus) -> String {
        switch status {
        case .active: return "flask.fill"
        case .paused: return "pause.circle"
        case .completed: return "checkmark.circle.fill"
        case .archived: return "archivebox"
        }
    }

    private func statusColor(_ status: ResearchProjectStatus) -> Color {
        switch status {
        case .active: return .blue
        case .paused: return .orange
        case .completed: return .green
        case .archived: return .secondary
        }
    }
}
