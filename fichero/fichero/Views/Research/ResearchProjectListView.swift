import SwiftUI

struct ResearchProjectListView: View {
    @EnvironmentObject var researchService: ResearchService

    @State private var showingNewProject = false
    @State private var newProjectName = ""
    @State private var projectToDelete: ResearchProject?
    @State private var showingDeleteConfirm = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer().frame(height: 12)
            projectList
            Divider()
            bottomToolbar
        }
    }

    @ViewBuilder
    private var projectList: some View {
        if researchService.isLoading {
            ProgressView()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if researchService.projects.isEmpty {
            ContentUnavailableView(
                "No Projects",
                systemImage: "flask",
                description: Text("Create a research project to get started.")
            )
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
        HStack {
            Button {
                showingNewProject = true
            } label: {
                Image(systemName: "plus")
            }
            .buttonStyle(.plain)
            .help("New Research Project")

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
                        let project = try? await researchService.createProject(name: name)
                        if let project { researchService.selectedProjectId = project.id }
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
