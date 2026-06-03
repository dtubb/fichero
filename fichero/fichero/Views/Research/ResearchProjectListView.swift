import SwiftUI

struct ResearchProjectListView: View {
    @EnvironmentObject var researchService: ResearchService
    @EnvironmentObject var documentStore: DocumentStore

    @State private var showingNewProject = false
    @State private var newProjectName = ""
    @State private var projectToDelete: ResearchProject?
    @State private var showingDeleteConfirm = false
    @State private var showingNewWorkspace = false
    @State private var newWorkspaceName = ""

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
            List(selection: $researchService.selectedProjectId) {
                Section("Research") {
                    ForEach(researchService.projects) { project in
                        projectRow(project)
                    }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
            .background(Color(NSColor.windowBackgroundColor))
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
                projectToDelete = project
                showingDeleteConfirm = true
            }
        }
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
                if let project = projectToDelete {
                    Task { try? await researchService.deleteProject(id: project.id) }
                }
            }
            Button("Cancel", role: .cancel) {}
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
