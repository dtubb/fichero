import Foundation
import Observation
import OSLog

/// Observable domain store for the Research module (#1904, mirrors `NoteStore`).
///
/// The single endpoint accessor for per-project research data. A view never
/// calls `ResearchService` directly: it observes the state below and dispatches
/// the named actions. Each action performs the typed write and then refreshes
/// the current project scope. Swapping explicit reloads for push updates (via
/// `apply(_:)`) once the per-library change-stream emits `research.*` events
/// is a no-op at every call site.
///
/// Domain data held per project scope: plans, tasks, steps, checklists,
/// sources, and research notes. Pure UI state (selected plan, expanded tasks,
/// input fields) remains in the view layer.
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class ResearchStore: ObservableDomainStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var plans: [ResearchPlan] = []
    private(set) var tasks: [ResearchTask] = []
    private(set) var stepsByTask: [String: [ResearchStep]] = [:]
    private(set) var checklists: [ResearchChecklist] = []
    private(set) var sources: [ResearchSource] = []
    private(set) var notes: [ResearchNote] = []
    private(set) var isLoading = false
    private(set) var loadedProjectId: String?
    /// True while the backend's research plan agent is running (#1729).
    private(set) var isGeneratingPlan = false
    /// Last plan-create failure, shown as an icon + detail affordance.
    private(set) var planFailure: String?

    /// Monotonic counter bumped on every applied `research.*` change event.
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING ResearchService wrapper, unchanged ───
    private let researchService: ResearchService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ResearchStore")

    init(researchService: ResearchService) {
        self.researchService = researchService
    }

    // MARK: - Load (the store, not the view, owns fetching)

    func load(forProject projectId: String, force: Bool = false) async {
        if !force, loadedProjectId == projectId { return }
        isLoading = true
        defer { isLoading = false }
        async let fetchedPlans = (try? await researchService.loadPlans(projectId: projectId)) ?? []
        async let fetchedChecklists = (try? await researchService.loadChecklists(projectId: projectId)) ?? []
        async let fetchedSources = (try? await researchService.loadSources(projectId: projectId)) ?? []
        async let fetchedNotes = (try? await researchService.loadNotes(projectId: projectId)) ?? []
        (plans, checklists, sources, notes) = await (fetchedPlans, fetchedChecklists, fetchedSources, fetchedNotes)
        loadedProjectId = projectId
        await reloadTasks(planId: plans.first?.id, projectId: projectId)
        log.debug("Loaded research data for project \(projectId, privacy: .public)")
    }

    func reloadTasks(planId: String?, projectId: String) async {
        if let planId {
            tasks = (try? await researchService.loadTasks(planId: planId)) ?? []
        } else {
            tasks = (try? await researchService.loadTasks(projectId: projectId)) ?? []
        }
    }

    func reload() async {
        guard let projectId = loadedProjectId else { return }
        await load(forProject: projectId, force: true)
    }

    // MARK: - Plan actions

    /// Create a plan. A non-empty `term` asks the backend to run its research
    /// plan agent (archives / locations / multilingual terms / summary) and
    /// store the result on the plan's metadata (#1729) — that call takes a few
    /// seconds, so `isGeneratingPlan` drives the progress affordance.
    @discardableResult
    func createPlan(projectId: String, name: String, term: String? = nil) async -> ResearchPlan? {
        let wantsAgent = term?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        if wantsAgent { isGeneratingPlan = true }
        defer { isGeneratingPlan = false }
        do {
            let plan = try await researchService.createPlan(
                projectId: projectId, name: name, term: term
            )
            plans.append(plan)
            planFailure = nil
            return plan
        } catch {
            // Surface, never swallow (#3302): the view shows an icon whose
            // detail is this message.
            planFailure = error.localizedDescription
            log.error("Plan create failed: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    func refreshPlan(_ id: String) async -> ResearchPlan? {
        guard let refreshed = try? await researchService.getPlan(id: id),
              let idx = plans.firstIndex(where: { $0.id == id }) else { return nil }
        plans[idx] = refreshed
        return refreshed
    }

    func activatePlan(_ id: String) async {
        guard let updated = try? await researchService.updatePlan(id: id, status: .active),
              let idx = plans.firstIndex(where: { $0.id == id }) else { return }
        plans[idx] = updated
    }

    func ensurePlanId(projectId: String) async -> String? {
        if let plan = try? await researchService.createPlan(
            projectId: projectId, name: "Research Plan"
        ) {
            plans.append(plan)
            return plan.id
        }
        return nil
    }

    // MARK: - Task actions

    @discardableResult
    func createTask(planId: String, name: String) async -> ResearchTask? {
        guard let task = try? await researchService.createTask(planId: planId, name: name) else {
            return nil
        }
        tasks.append(task)
        return task
    }

    func cycleTaskStatus(_ task: ResearchTask, to nextStatus: ResearchTaskStatus) async {
        guard (try? await researchService.updateTask(id: task.id, status: nextStatus)) != nil,
              let refreshed = try? await researchService.getTask(id: task.id),
              let idx = tasks.firstIndex(where: { $0.id == task.id }) else { return }
        tasks[idx] = refreshed
    }

    // MARK: - Step actions

    func loadSteps(forTaskId taskId: String) async {
        stepsByTask[taskId] = (try? await researchService.loadSteps(taskId: taskId)) ?? []
    }

    @discardableResult
    func addStep(toTask task: ResearchTask) async -> ResearchStep? {
        let order = stepsByTask[task.id]?.count ?? 0
        guard let step = try? await researchService.createStep(
            taskId: task.id, tool: .webSearch,
            label: "Search step \(order + 1)", orderIndex: order
        ) else { return nil }
        stepsByTask[task.id, default: []].append(step)
        return step
    }

    func toggleStep(task: ResearchTask, step: ResearchStep) async {
        let newStatus: ResearchStepStatus = step.status == .completed ? .pending : .completed
        guard let updated = try? await researchService.updateStep(id: step.id, status: newStatus),
              let idx = stepsByTask[task.id]?.firstIndex(where: { $0.id == step.id }) else { return }
        stepsByTask[task.id]?[idx] = updated
    }

    // MARK: - Checklist actions

    @discardableResult
    func createChecklist(projectId: String, title: String) async -> ResearchChecklist? {
        guard let checklist = try? await researchService.createChecklist(
            projectId: projectId, title: title, itemLabels: ["Verify"]
        ) else { return nil }
        checklists.append(checklist)
        return checklist
    }

    func toggleChecklistItem(checklist: ResearchChecklist, item: ChecklistItem) async {
        guard let updated = try? await researchService.toggleChecklistItem(
            checklistId: checklist.id, itemId: item.id, checked: !item.checked
        ), let idx = checklists.firstIndex(where: { $0.id == checklist.id }) else { return }
        checklists[idx] = updated
    }

    // MARK: - Source actions

    @discardableResult
    func createSource(projectId: String, label: String, url: String?) async -> ResearchSource? {
        let isURL = url != nil
        let sourceType = isURL ? "url" : "folder"
        guard let source = try? await researchService.createSource(
            projectId: projectId, label: label, sourceType: sourceType, url: url
        ) else { return nil }
        sources.append(source)
        return source
    }

    // MARK: - Note actions

    @discardableResult
    func createNote(projectId: String, content: String) async -> ResearchNote? {
        guard let note = try? await researchService.createNote(
            projectId: projectId, content: content
        ) else { return nil }
        notes.insert(note, at: 0)
        return note
    }

    func getNote(id: String) async -> ResearchNote? {
        try? await researchService.getNote(id: id)
    }

    func updateNote(id: String, content: String) async -> ResearchNote? {
        guard (try? await researchService.updateNote(id: id, content: content)) != nil,
              let refreshed = try? await researchService.getNote(id: id),
              let idx = notes.firstIndex(where: { $0.id == id }) else { return nil }
        notes[idx] = refreshed
        return notes[idx]
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "research" }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
        switch event.verb {
        case "created", "updated", "deleted":
            scheduleReload()
        default:
            break
        }
    }

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for create/update/delete) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()
}
