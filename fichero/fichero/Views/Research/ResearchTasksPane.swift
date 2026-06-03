import SwiftUI

struct ResearchTasksPane: View {
    var project: ResearchProject
    @EnvironmentObject var researchService: ResearchService

    @State private var plans: [ResearchPlan] = []
    @State private var selectedPlanId: String?
    @State private var tasks: [ResearchTask] = []
    @State private var stepsByTask: [String: [ResearchStep]] = [:]
    @State private var expandedTaskIds: Set<String> = []
    @State private var checklists: [ResearchChecklist] = []
    @State private var sources: [ResearchSource] = []
    @State private var notes: [ResearchNote] = []
    @State private var isLoading = false
    @State private var selectedTab = 0

    @State private var newTaskText = ""
    @State private var newChecklistText = ""
    @State private var newSourceText = ""
    @State private var newNoteText = ""
    @State private var editingNoteId: String?
    @State private var editingNoteText = ""

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("Tasks").tag(0)
                Text("Checklists").tag(1)
                Text("Sources").tag(2)
                Text("Notes").tag(3)
            }
            .pickerStyle(.segmented)
            .padding(8)

            Divider()

            if isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                switch selectedTab {
                case 0: tasksTab
                case 1: checklistsTab
                case 2: sourcesTab
                default: notesTab
                }
            }
        }
        .task(id: project.id) { await reload() }
    }
}

// MARK: - Views & actions
// Split into an extension to keep the primary type body small (SwiftLint
// type_body_length); `private` members stay file-visible across same-file
// extensions.

extension ResearchTasksPane {

    // MARK: - Tasks tab

    @ViewBuilder
    private var tasksTab: some View {
        VStack(spacing: 0) {
            planPicker
            Divider()
            if tasks.isEmpty {
                ContentUnavailableView(
                    "No Tasks",
                    systemImage: "checklist",
                    description: Text("Add a task below or run the research workflow.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(tasks) { task in
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

    private var planPicker: some View {
        HStack(spacing: 8) {
            Image(systemName: "list.bullet.rectangle")
                .foregroundStyle(.secondary)
            Menu {
                ForEach(plans) { plan in
                    Button {
                        Task { await selectPlan(plan.id) }
                    } label: {
                        Label(plan.name, systemImage: plan.id == selectedPlanId ? "checkmark" : "")
                    }
                }
                if let id = selectedPlanId {
                    Divider()
                    Button("Mark Plan Active") { Task { await activatePlan(id) } }
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

    private var currentPlanName: String {
        if let id = selectedPlanId, let plan = plans.first(where: { $0.id == id }) {
            return plan.name
        }
        return "All Tasks"
    }

    private func taskRow(_ task: ResearchTask) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Button {
                Task { await cycleStatus(task) }
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
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func stepsSection(_ task: ResearchTask) -> some View {
        let steps = stepsByTask[task.id] ?? []
        ForEach(steps) { step in
            HStack(spacing: 8) {
                Button {
                    Task { await toggleStep(task: task, step: step) }
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
            Task { await addStep(task) }
        } label: {
            Label("Add step", systemImage: "plus.circle")
                .font(.caption)
        }
        .buttonStyle(.plain)
        .padding(.leading, 28)
    }

    // MARK: - Checklists tab

    @ViewBuilder
    private var checklistsTab: some View {
        VStack(spacing: 0) {
            if checklists.isEmpty {
                ContentUnavailableView(
                    "No Checklists",
                    systemImage: "checklist.checked",
                    description: Text("Add a verification checklist below.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(checklists) { checklist in
                            checklistCard(checklist)
                        }
                    }
                    .padding(8)
                }
            }
            composer(placeholder: "New checklist…", text: $newChecklistText) { submitChecklist() }
        }
    }

    private func checklistCard(_ checklist: ResearchChecklist) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(checklist.title).font(.headline)
            ForEach(checklist.items) { item in
                Button {
                    Task { await toggleChecklistItem(checklist: checklist, item: item) }
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
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Sources tab

    @ViewBuilder
    private var sourcesTab: some View {
        VStack(spacing: 0) {
            if sources.isEmpty {
                ContentUnavailableView(
                    "No Sources",
                    systemImage: "link",
                    description: Text("Curate search sources for this project.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(sources) { source in
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

    private var notesTab: some View {
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

            composer(placeholder: "Add a note…", text: $newNoteText) { submitNote() }
        }
    }

    @ViewBuilder
    private func noteCard(_ note: ResearchNote) -> some View {
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
            .background(Color(NSColor.controlBackgroundColor))
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
            .background(Color(NSColor.controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .onTapGesture { beginEditing(note) }
        }
    }

    // MARK: - Shared composer

    private func composer(
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
            .disabled(text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8)
    }

    // MARK: - Loading

    private func reload() async {
        isLoading = true
        plans = (try? await researchService.loadPlans(projectId: project.id)) ?? []
        if selectedPlanId == nil { selectedPlanId = plans.first?.id }
        await reloadTasks()
        checklists = (try? await researchService.loadChecklists(projectId: project.id)) ?? []
        sources = (try? await researchService.loadSources(projectId: project.id)) ?? []
        notes = (try? await researchService.loadNotes(projectId: project.id)) ?? []
        isLoading = false
    }

    private func reloadTasks() async {
        if let planId = selectedPlanId {
            tasks = (try? await researchService.loadTasks(planId: planId)) ?? []
        } else {
            tasks = (try? await researchService.loadTasks(projectId: project.id)) ?? []
        }
    }

    // MARK: - Plan actions

    private func selectPlan(_ id: String) async {
        // Refresh canonical plan detail, then scope tasks to it.
        if let refreshed = try? await researchService.getPlan(id: id),
            let idx = plans.firstIndex(where: { $0.id == id }) {
            plans[idx] = refreshed
        }
        selectedPlanId = id
        await reloadTasks()
    }

    private func createPlan() async {
        let name = "Plan \(plans.count + 1)"
        if let plan = try? await researchService.createPlan(projectId: project.id, name: name) {
            plans.append(plan)
            selectedPlanId = plan.id
            await reloadTasks()
        }
    }

    private func activatePlan(_ id: String) async {
        if let updated = try? await researchService.updatePlan(id: id, status: .active),
            let idx = plans.firstIndex(where: { $0.id == id }) {
            plans[idx] = updated
        }
    }

    private func ensurePlanId() async -> String? {
        if let id = selectedPlanId { return id }
        if let plan = try? await researchService.createPlan(projectId: project.id, name: "Research Plan") {
            plans.append(plan)
            selectedPlanId = plan.id
            return plan.id
        }
        return nil
    }

    // MARK: - Task actions

    private func submitTask() {
        let text = newTaskText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newTaskText = ""
        Task {
            guard let planId = await ensurePlanId() else { return }
            if let task = try? await researchService.createTask(planId: planId, name: text) {
                tasks.append(task)
            }
        }
    }

    private func cycleStatus(_ task: ResearchTask) async {
        let next = nextStatus(task.status)
        if (try? await researchService.updateTask(id: task.id, status: next)) != nil,
            let refreshed = try? await researchService.getTask(id: task.id),
            let idx = tasks.firstIndex(where: { $0.id == task.id }) {
            tasks[idx] = refreshed
        }
    }

    private func nextStatus(_ status: ResearchTaskStatus) -> ResearchTaskStatus {
        switch status {
        case .pending: return .inProgress
        case .inProgress: return .completed
        case .completed: return .pending
        case .blocked: return .inProgress
        case .cancelled: return .pending
        }
    }

    // MARK: - Step actions

    private func toggleSteps(_ task: ResearchTask) async {
        if expandedTaskIds.contains(task.id) {
            expandedTaskIds.remove(task.id)
        } else {
            expandedTaskIds.insert(task.id)
            stepsByTask[task.id] = (try? await researchService.loadSteps(taskId: task.id)) ?? []
        }
    }

    private func addStep(_ task: ResearchTask) async {
        let order = (stepsByTask[task.id]?.count ?? 0)
        if let step = try? await researchService.createStep(
            taskId: task.id, tool: .webSearch, label: "Search step \(order + 1)", orderIndex: order
        ) {
            stepsByTask[task.id, default: []].append(step)
        }
    }

    private func toggleStep(task: ResearchTask, step: ResearchStep) async {
        let newStatus: ResearchStepStatus = step.status == .completed ? .pending : .completed
        if let updated = try? await researchService.updateStep(id: step.id, status: newStatus),
            let idx = stepsByTask[task.id]?.firstIndex(where: { $0.id == step.id }) {
            stepsByTask[task.id]?[idx] = updated
        }
    }

    // MARK: - Checklist actions

    private func submitChecklist() {
        let text = newChecklistText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newChecklistText = ""
        Task {
            if let checklist = try? await researchService.createChecklist(
                projectId: project.id, title: text, itemLabels: ["Verify"]
            ) {
                checklists.append(checklist)
            }
        }
    }

    private func toggleChecklistItem(checklist: ResearchChecklist, item: ChecklistItem) async {
        if let updated = try? await researchService.toggleChecklistItem(
            checklistId: checklist.id, itemId: item.id, checked: !item.checked
        ), let idx = checklists.firstIndex(where: { $0.id == checklist.id }) {
            checklists[idx] = updated
        }
    }

    // MARK: - Source actions

    private func submitSource() {
        let text = newSourceText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newSourceText = ""
        Task {
            let isURL = text.lowercased().hasPrefix("http")
            if let source = try? await researchService.createSource(
                projectId: project.id, label: text,
                sourceType: isURL ? "url" : "folder", url: isURL ? text : nil
            ) {
                sources.append(source)
            }
        }
    }

    // MARK: - Note actions

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

    private func beginEditing(_ note: ResearchNote) {
        editingNoteId = note.id
        editingNoteText = note.content
    }

    private func saveNoteEdit(_ note: ResearchNote) async {
        let text = editingNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { editingNoteId = nil; return }
        if (try? await researchService.updateNote(id: note.id, content: text)) != nil,
            let refreshed = try? await researchService.getNote(id: note.id),
            let idx = notes.firstIndex(where: { $0.id == note.id }) {
            notes[idx] = refreshed
        }
        editingNoteId = nil
    }

    // MARK: - Status presentation

    private func taskIcon(_ status: ResearchTaskStatus) -> String {
        switch status {
        case .pending: return "circle"
        case .inProgress: return "circle.dotted"
        case .completed: return "checkmark.circle.fill"
        case .blocked: return "exclamationmark.circle"
        case .cancelled: return "xmark.circle"
        }
    }

    private func taskColor(_ status: ResearchTaskStatus) -> Color {
        switch status {
        case .pending: return .secondary
        case .inProgress: return .blue
        case .completed: return .green
        case .blocked: return .orange
        case .cancelled: return .secondary
        }
    }
}
