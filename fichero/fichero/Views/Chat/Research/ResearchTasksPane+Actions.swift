import SwiftUI

// MARK: - Loading & actions
// Split into an extension to keep the primary type body small (SwiftLint
// type_body_length / file_length). Members are `internal` so sibling-file
// extensions can reference them.

extension ResearchTasksPane {

    // MARK: - Loading

    func reload() async {
        await researchStore.load(forProject: project.id, force: true)
        if selectedPlanId == nil { selectedPlanId = researchStore.plans.first?.id }
        await researchStore.reloadTasks(planId: selectedPlanId, projectId: project.id)
    }

    // MARK: - Plan actions

    func selectPlan(_ id: String) async {
        _ = await researchStore.refreshPlan(id)
        selectedPlanId = id
        await researchStore.reloadTasks(planId: id, projectId: project.id)
    }

    func createPlan() async {
        let name = "Plan \(researchStore.plans.count + 1)"
        if let plan = await researchStore.createPlan(projectId: project.id, name: name) {
            selectedPlanId = plan.id
            await researchStore.reloadTasks(planId: plan.id, projectId: project.id)
        }
    }

    /// Open the AI plan composer with a sensible default name (#1729).
    func presentPlanComposer() {
        newPlanName = "Plan \(researchStore.plans.count + 1)"
        newPlanTerm = ""
        isPlanComposerPresented = true
    }

    /// Create a plan WITH a research term, so the backend runs its plan agent
    /// and returns archives / locations / multilingual terms / summary (#1729).
    func generatePlanWithAI() async {
        let term = newPlanTerm.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !term.isEmpty else { return }
        let name = newPlanName.trimmingCharacters(in: .whitespacesAndNewlines)
        if let plan = await researchStore.createPlan(
            projectId: project.id,
            name: name.isEmpty ? term : name,
            term: term
        ) {
            isPlanComposerPresented = false
            selectedPlanId = plan.id
            await researchStore.reloadTasks(planId: plan.id, projectId: project.id)
        }
    }

    func ensurePlanId() async -> String? {
        if let id = selectedPlanId { return id }
        let id = await researchStore.ensurePlanId(projectId: project.id)
        selectedPlanId = id
        return id
    }

    // MARK: - Task actions

    func submitTask() {
        let text = newTaskText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newTaskText = ""
        Task {
            guard let planId = await ensurePlanId() else { return }
            _ = await researchStore.createTask(planId: planId, name: text)
        }
    }

    func nextStatus(_ status: ResearchTaskStatus) -> ResearchTaskStatus {
        switch status {
        case .pending: return .inProgress
        case .inProgress: return .completed
        case .completed: return .pending
        case .blocked: return .inProgress
        case .cancelled: return .pending
        }
    }

    // MARK: - Step actions

    func toggleSteps(_ task: ResearchTask) async {
        if expandedTaskIds.contains(task.id) {
            expandedTaskIds.remove(task.id)
        } else {
            expandedTaskIds.insert(task.id)
            await researchStore.loadSteps(forTaskId: task.id)
        }
    }

    // MARK: - Checklist actions

    func submitChecklist() {
        let text = newChecklistText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newChecklistText = ""
        Task {
            _ = await researchStore.createChecklist(projectId: project.id, title: text)
        }
    }

    // MARK: - Source actions

    func submitSource() {
        let text = newSourceText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newSourceText = ""
        Task {
            let isURL = text.lowercased().hasPrefix("http")
            _ = await researchStore.createSource(
                projectId: project.id, label: text,
                url: isURL ? text : nil
            )
        }
    }

    // MARK: - Note actions

    func submitNote() {
        let text = newNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        newNoteText = ""
        Task {
            _ = await researchStore.createNote(projectId: project.id, content: text)
        }
    }

    func beginEditing(_ note: ResearchNote) {
        editingNoteId = note.id
        editingNoteText = note.content
    }

    func saveNoteEdit(_ note: ResearchNote) async {
        let text = editingNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { editingNoteId = nil; return }
        _ = await researchStore.updateNote(id: note.id, content: text)
        editingNoteId = nil
    }

    // MARK: - Status presentation

    func taskIcon(_ status: ResearchTaskStatus) -> String {
        switch status {
        case .pending: return "circle"
        case .inProgress: return "circle.dotted"
        case .completed: return "checkmark.circle.fill"
        case .blocked: return "exclamationmark.circle"
        case .cancelled: return "xmark.circle"
        }
    }

    func taskColor(_ status: ResearchTaskStatus) -> Color {
        switch status {
        case .pending: return .secondary
        case .inProgress: return .blue
        case .completed: return .green
        case .blocked: return .orange
        case .cancelled: return .secondary
        }
    }
}
