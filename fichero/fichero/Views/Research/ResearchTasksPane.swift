import SwiftUI

struct ResearchTasksPane: View {
    var project: ResearchProject
    @EnvironmentObject var researchService: ResearchService

    @State private var plans: [ResearchPlan] = []
    @State private var tasks: [ResearchTask] = []
    @State private var notes: [ResearchNote] = []
    @State private var isLoading = false
    @State private var selectedTab = 0
    @State private var newNoteText = ""

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("Tasks").tag(0)
                Text("Notes").tag(1)
            }
            .pickerStyle(.segmented)
            .padding(8)

            Divider()

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if selectedTab == 0 {
                tasksList
            } else {
                notesList
            }
        }
        .task(id: project.id) { await reload() }
    }

    // MARK: - Tasks tab

    @ViewBuilder
    private var tasksList: some View {
        if tasks.isEmpty {
            ContentUnavailableView(
                "No Tasks",
                systemImage: "checklist",
                description: Text("Add tasks via the research workflow.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(tasks) { task in
                taskRow(task)
            }
            .listStyle(.plain)
        }
    }

    private func taskRow(_ task: ResearchTask) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: taskIcon(task.status))
                .foregroundStyle(taskColor(task.status))
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(task.name)
                    .font(.body)
                if !task.description.isEmpty {
                    Text(task.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Text(task.status.label)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    // MARK: - Notes tab

    private var notesList: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(notes) { note in
                        noteCard(note)
                    }
                }
                .padding(8)
            }

            Divider()

            HStack(spacing: 8) {
                TextField("Add a note…", text: $newNoteText, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...3)
                    .onSubmit { submitNote() }

                Button {
                    submitNote()
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title3)
                }
                .buttonStyle(.plain)
                .disabled(newNoteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(8)
        }
    }

    private func noteCard(_ note: ResearchNote) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(note.content)
                .font(.body)
            Text(note.createdAt, style: .relative)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Actions

    private func reload() async {
        isLoading = true
        async let plansResult = try? researchService.loadPlans(projectId: project.id)
        async let tasksResult = try? researchService.loadTasks(projectId: project.id)
        async let notesResult = try? researchService.loadNotes(projectId: project.id)
        plans = await plansResult ?? []
        tasks = await tasksResult ?? []
        notes = await notesResult ?? []
        isLoading = false
    }

    private func submitNote() {
        let text = newNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newNoteText = ""
        Task {
            if let note = try? await researchService.createNote(projectId: project.id, content: text) {
                notes.insert(note, at: 0)
            }
        }
    }

    private func taskIcon(_ status: ResearchTaskStatus) -> String {
        switch status {
        case .pending: return "circle"
        case .in_progress: return "circle.dotted"
        case .completed: return "checkmark.circle.fill"
        case .blocked: return "exclamationmark.circle"
        case .cancelled: return "xmark.circle"
        }
    }

    private func taskColor(_ status: ResearchTaskStatus) -> Color {
        switch status {
        case .pending: return .secondary
        case .in_progress: return .blue
        case .completed: return .green
        case .blocked: return .orange
        case .cancelled: return .secondary
        }
    }
}
