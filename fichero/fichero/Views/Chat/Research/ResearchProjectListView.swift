import SwiftUI

struct ResearchProjectListView: View {
    @Environment(ResearchService.self) var researchService

    @State private var showingNewProject = false
    @State private var newProjectName = ""
    @State private var projectsToDelete: [ResearchProject] = []
    @State private var showingDeleteConfirm = false
    @State private var selectedProjectIds: Set<String> = []

    var body: some View {
        VStack(spacing: 0) {
            Spacer().frame(height: 12)
            projectList
            Divider()
            bottomToolbar
        }
        // Load existing projects when the Research surface appears. Without
        // this the list was always empty and previously-created projects
        // were invisible — which read as "can't add" (#1614).
        //
        // Workspaces section DELETED (#4705 5a), not moved anywhere: a
        // workspace is already an ordinary folder `Document` (`isWorkspace:
        // Bool`) and already appears in the ordinary library tree wherever
        // its parent folder is visible — a SECOND, flat "all my workspaces"
        // list here would show the same folder twice with the same id
        // (undefined SwiftUI List selection/diffing), and duplicates the
        // tree the Library pane already shows. If a flat "all workspaces"
        // view is ever wanted, it is a Library filter/smart search, not
        // sidebar plumbing.
        .task {
            await researchService.loadProjects()
        }
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

            // Workspaces are created from the sidebar's creation menu
            // (`SidebarCreationHandlers.createNewWorkspace()`), not here.

            Spacer()
        }
        .padding(.horizontal, 12)
        .frame(height: 32)
        .popover(isPresented: $showingNewProject) {
            newProjectForm
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
