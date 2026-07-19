import SwiftUI

// MARK: - Tab views & subviews
// Split into an extension to keep the primary type body small (SwiftLint
// type_body_length / file_length). Members are `internal` so sibling-file
// extensions can reference them.

extension ResearchTasksPane {

    // MARK: - Tasks tab

    @ViewBuilder
    var tasksTab: some View {
        VStack(spacing: 0) {
            planPicker
            Divider()
            if researchStore.tasks.isEmpty {
                ContentUnavailableView(
                    "No Tasks",
                    systemImage: "checklist",
                    description: Text("Add a task below or run the research workflow.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(researchStore.tasks) { task in
                        taskRow(task)
                        if expandedTaskIds.contains(task.id) {
                            stepsSection(task)
                        }
                    }
                }
                .listStyle(.plain)
            }
            composer(placeholder: "Add a task…", text: $newTaskText) { submitTask() }
        }
    }

    var planPicker: some View {
        HStack(spacing: 8) {
            Image(systemName: "list.bullet.rectangle")
                .foregroundStyle(.secondary)
            Menu {
                ForEach(researchStore.plans) { plan in
                    Button {
                        Task { await selectPlan(plan.id) }
                    } label: {
                        Label(plan.name, systemImage: plan.id == selectedPlanId ? "checkmark" : "")
                    }
                }
                if let id = selectedPlanId {
                    Divider()
                    Button("Mark Plan Active") { Task { await researchStore.activatePlan(id) } }
                }
                Divider()
                Button("New Plan") { Task { await createPlan() } }
            } label: {
                Text(currentPlanName)
                    .font(.subheadline)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .menuStyle(.borderlessButton)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    var currentPlanName: String {
        if let id = selectedPlanId, let plan = researchStore.plans.first(where: { $0.id == id }) {
            return plan.name
        }
        return "All Tasks"
    }

    func taskRow(_ task: ResearchTask) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Button {
                Task { await researchStore.cycleTaskStatus(task, to: nextStatus(task.status)) }
            } label: {
                Image(systemName: taskIcon(task.status))
                    .foregroundStyle(taskColor(task.status))
                    .frame(width: 16)
            }
            .buttonStyle(.plain)
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
            Spacer()
            Button {
                Task { await toggleSteps(task) }
            } label: {
                Image(systemName: expandedTaskIds.contains(task.id) ? "chevron.down" : "chevron.right")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help(expandedTaskIds.contains(task.id) ? "Hide this task's steps" : "Show this task's steps")
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    func stepsSection(_ task: ResearchTask) -> some View {
        let steps = researchStore.stepsByTask[task.id] ?? []
        ForEach(steps) { step in
            HStack(spacing: 8) {
                Button {
                    Task { await researchStore.toggleStep(task: task, step: step) }
                } label: {
                    Image(systemName: step.status == .completed ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(step.status == .completed ? .green : .secondary)
                }
                .buttonStyle(.plain)
                Text(step.label).font(.caption)
                Spacer()
                Text(step.tool.label).font(.caption2).foregroundStyle(.tertiary)
            }
            .padding(.leading, 28)
        }
        Button {
            Task { await researchStore.addStep(toTask: task) }
        } label: {
            Label("Add step", systemImage: "plus.circle")
                .font(.caption)
        }
        .buttonStyle(.plain)
        .padding(.leading, 28)
    }

    // MARK: - Checklists tab

    @ViewBuilder
    var checklistsTab: some View {
        VStack(spacing: 0) {
            if researchStore.checklists.isEmpty {
                ContentUnavailableView(
                    "No Checklists",
                    systemImage: "checklist.checked",
                    description: Text("Add a verification checklist below.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(researchStore.checklists) { checklist in
                            checklistCard(checklist)
                        }
                    }
                    .padding(8)
                }
            }
            composer(placeholder: "New checklist…", text: $newChecklistText) { submitChecklist() }
        }
    }

    func checklistCard(_ checklist: ResearchChecklist) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(checklist.title).font(.headline)
            ForEach(checklist.items) { item in
                Button {
                    Task { await researchStore.toggleChecklistItem(checklist: checklist, item: item) }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: item.checked ? "checkmark.square.fill" : "square")
                            .foregroundStyle(item.checked ? .green : .secondary)
                        Text(item.label).font(.body)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(platformColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Sources tab

    @ViewBuilder
    var sourcesTab: some View {
        VStack(spacing: 0) {
            if researchStore.sources.isEmpty {
                ContentUnavailableView(
                    "No Sources",
                    systemImage: "link",
                    description: Text("Curate search sources for this project.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(researchStore.sources) { source in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(source.label).font(.body)
                        if let url = source.url, !url.isEmpty {
                            Text(url).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
                .listStyle(.plain)
            }
            composer(placeholder: "Add source URL…", text: $newSourceText) { submitSource() }
        }
    }

    // MARK: - Notes tab

    var notesTab: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(researchStore.notes) { note in
                        noteCard(note)
                    }
                }
                .padding(8)
            }

            Divider()

            composer(placeholder: "Add a note…", text: $newNoteText) { submitNote() }
        }
    }

    @ViewBuilder
    func noteCard(_ note: ResearchNote) -> some View {
        if editingNoteId == note.id {
            VStack(alignment: .leading, spacing: 6) {
                TextField("Edit note…", text: $editingNoteText, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...6)
                HStack {
                    Button("Cancel") { editingNoteId = nil }
                    Spacer()
                    Button("Save") { Task { await saveNoteEdit(note) } }
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding(8)
            .background(Color(platformColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Text(note.content)
                    .font(.body)
                Text(note.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(platformColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .onTapGesture { beginEditing(note) }
        }
    }

    // MARK: - Shared composer

    func composer(
        placeholder: String, text: Binding<String>, onSubmit: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 8) {
            TextField(placeholder, text: text, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .onSubmit(onSubmit)

            Button(action: onSubmit) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title3)
            }
            .buttonStyle(.plain)
            .help("Submit")
            .disabled(text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8)
    }
}
