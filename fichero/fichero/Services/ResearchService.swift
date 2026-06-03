import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ResearchService")

// MARK: - Request types (mirrors backend research_models.py)

private struct ProjectCreateRequest: Codable {
    var name: String
    var description: String
    var libraryDestinationFolderId: String?

    enum CodingKeys: String, CodingKey {
        case name, description
        case libraryDestinationFolderId = "library_destination_folder_id"
    }
}

private struct ProjectUpdateRequest: Codable {
    var name: String?
    var description: String?
    var status: String?
    var libraryDestinationFolderId: String?

    enum CodingKeys: String, CodingKey {
        case name, description, status
        case libraryDestinationFolderId = "library_destination_folder_id"
    }
}

private struct NoteCreateRequest: Codable {
    var projectId: String
    var taskId: String?
    var noteType: String
    var content: String
    var tags: [String]

    enum CodingKeys: String, CodingKey {
        case content, tags
        case projectId = "project_id"
        case taskId = "task_id"
        case noteType = "note_type"
    }
}

private struct ResearchListResponse<T: Codable>: Codable {
    var items: [T]
    var count: Int
}

private struct WebSearchRequest: Codable {
    var query: String
    var maxResults: Int
    enum CodingKeys: String, CodingKey {
        case query
        case maxResults = "max_results"
    }
}

private struct WebSearchResult: Codable {
    var results: [WebSearchResultItem]
}

// MARK: - Plan / Task / Step / Checklist / Source / Note request bodies

private struct PlanCreateRequest: Codable {
    var projectId: String
    var name: String
    var description: String
    enum CodingKeys: String, CodingKey {
        case name, description
        case projectId = "project_id"
    }
}

private struct PlanUpdateRequest: Codable {
    var name: String?
    var description: String?
    var status: String?
}

private struct TaskCreateRequest: Codable {
    var planId: String
    var name: String
    var description: String
    var priority: Int
    enum CodingKeys: String, CodingKey {
        case name, description, priority
        case planId = "plan_id"
    }
}

private struct TaskUpdateRequest: Codable {
    var name: String?
    var description: String?
    var status: String?
    var priority: Int?
}

private struct StepCreateRequest: Codable {
    var taskId: String
    var tool: String
    var label: String
    var description: String
    var orderIndex: Int
    enum CodingKeys: String, CodingKey {
        case tool, label, description
        case taskId = "task_id"
        case orderIndex = "order_index"
    }
}

private struct StepUpdateRequest: Codable {
    var label: String?
    var description: String?
    var status: String?
    var orderIndex: Int?
    enum CodingKeys: String, CodingKey {
        case label, description, status
        case orderIndex = "order_index"
    }
}

private struct ChecklistItemCreate: Codable {
    var label: String
}

private struct ChecklistCreateRequest: Codable {
    var projectId: String
    var taskId: String?
    var title: String
    var items: [ChecklistItemCreate]
    enum CodingKeys: String, CodingKey {
        case title, items
        case projectId = "project_id"
        case taskId = "task_id"
    }
}

private struct ChecklistItemToggleRequest: Codable {
    var checked: Bool
    var notes: String
}

private struct SearchSourceCreateRequest: Codable {
    var projectId: String
    var sourceType: String
    var label: String
    var url: String?
    var description: String
    enum CodingKeys: String, CodingKey {
        case label, url, description
        case projectId = "project_id"
        case sourceType = "source_type"
    }
}

private struct NoteUpdateRequest: Codable {
    var content: String?
    var noteType: String?
    var tags: [String]?
    enum CodingKeys: String, CodingKey {
        case content, tags
        case noteType = "note_type"
    }
}

// MARK: - ResearchService

@MainActor
class ResearchService: ObservableObject {
    private let apiClient: APIClient

    @Published var projects: [ResearchProject] = []
    @Published var selectedProjectId: String?
    @Published var isLoading = false
    @Published var error: String?

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Projects

    func loadProjects() async {
        isLoading = true
        error = nil
        do {
            let response: ResearchListResponse<ResearchProject> = try await apiClient.get("/api/research/projects")
            projects = response.items
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load research projects: \(error)")
        }
        isLoading = false
    }

    func createProject(
        name: String, description: String = "", folderDestinationId: String? = nil
    ) async throws -> ResearchProject {
        let req = ProjectCreateRequest(
            name: name, description: description, libraryDestinationFolderId: folderDestinationId
        )
        let project: ResearchProject = try await apiClient.post("/api/research/projects", body: req)
        projects.append(project)
        return project
    }

    func updateProject(_ project: ResearchProject) async throws {
        let req = ProjectUpdateRequest(
            name: project.name,
            description: project.description,
            status: project.status.rawValue,
            libraryDestinationFolderId: project.libraryDestinationFolderId
        )
        let updated: ResearchProject = try await apiClient.patch("/api/research/projects/\(project.id)", body: req)
        if let idx = projects.firstIndex(where: { $0.id == project.id }) {
            projects[idx] = updated
        }
    }

    func deleteProject(id: String) async throws {
        try await apiClient.delete("/api/research/projects/\(id)")
        projects.removeAll { $0.id == id }
    }

    // MARK: - Plans

    func loadPlans(projectId: String) async throws -> [ResearchPlan] {
        let response: ResearchListResponse<ResearchPlan> = try await apiClient.get(
            "/api/research/projects/\(projectId)/plans"
        )
        return response.items
    }

    func createPlan(projectId: String, name: String, description: String = "") async throws -> ResearchPlan {
        let req = PlanCreateRequest(projectId: projectId, name: name, description: description)
        return try await apiClient.post("/api/research/plans", body: req)
    }

    func getPlan(id: String) async throws -> ResearchPlan {
        try await apiClient.get("/api/research/plans/\(id)")
    }

    func updatePlan(
        id: String, name: String? = nil, description: String? = nil, status: ResearchPlanStatus? = nil
    ) async throws -> ResearchPlan {
        let req = PlanUpdateRequest(name: name, description: description, status: status?.rawValue)
        return try await apiClient.patch("/api/research/plans/\(id)", body: req)
    }

    // MARK: - Tasks

    func loadTasks(projectId: String) async throws -> [ResearchTask] {
        let response: ResearchListResponse<ResearchTask> = try await apiClient.get(
            "/api/research/projects/\(projectId)/tasks"
        )
        return response.items
    }

    func loadTasks(planId: String) async throws -> [ResearchTask] {
        let response: ResearchListResponse<ResearchTask> = try await apiClient.get(
            "/api/research/plans/\(planId)/tasks"
        )
        return response.items
    }

    func createTask(
        planId: String, name: String, description: String = "", priority: Int = 0
    ) async throws -> ResearchTask {
        let req = TaskCreateRequest(planId: planId, name: name, description: description, priority: priority)
        return try await apiClient.post("/api/research/tasks", body: req)
    }

    func getTask(id: String) async throws -> ResearchTask {
        try await apiClient.get("/api/research/tasks/\(id)")
    }

    func updateTask(
        id: String, name: String? = nil, description: String? = nil,
        status: ResearchTaskStatus? = nil, priority: Int? = nil
    ) async throws -> ResearchTask {
        let req = TaskUpdateRequest(
            name: name, description: description, status: status?.rawValueForAPI, priority: priority
        )
        return try await apiClient.patch("/api/research/tasks/\(id)", body: req)
    }

    // MARK: - Steps

    func loadSteps(taskId: String) async throws -> [ResearchStep] {
        let response: ResearchListResponse<ResearchStep> = try await apiClient.get(
            "/api/research/tasks/\(taskId)/steps"
        )
        return response.items
    }

    func createStep(
        taskId: String, tool: ResearchStepTool, label: String,
        description: String = "", orderIndex: Int = 0
    ) async throws -> ResearchStep {
        let req = StepCreateRequest(
            taskId: taskId, tool: tool.rawValue, label: label,
            description: description, orderIndex: orderIndex
        )
        return try await apiClient.post("/api/research/steps", body: req)
    }

    func updateStep(
        id: String, label: String? = nil, description: String? = nil,
        status: ResearchStepStatus? = nil, orderIndex: Int? = nil
    ) async throws -> ResearchStep {
        let req = StepUpdateRequest(
            label: label, description: description, status: status?.rawValue, orderIndex: orderIndex
        )
        return try await apiClient.patch("/api/research/steps/\(id)", body: req)
    }

    // MARK: - Checklists

    func loadChecklists(projectId: String) async throws -> [ResearchChecklist] {
        let response: ResearchListResponse<ResearchChecklist> = try await apiClient.get(
            "/api/research/projects/\(projectId)/checklists"
        )
        return response.items
    }

    func createChecklist(
        projectId: String, title: String, itemLabels: [String] = [], taskId: String? = nil
    ) async throws -> ResearchChecklist {
        let req = ChecklistCreateRequest(
            projectId: projectId, taskId: taskId, title: title,
            items: itemLabels.map { ChecklistItemCreate(label: $0) }
        )
        return try await apiClient.post("/api/research/checklists", body: req)
    }

    func toggleChecklistItem(
        checklistId: String, itemId: String, checked: Bool, notes: String = ""
    ) async throws -> ResearchChecklist {
        let req = ChecklistItemToggleRequest(checked: checked, notes: notes)
        return try await apiClient.patch(
            "/api/research/checklists/\(checklistId)/items/\(itemId)", body: req
        )
    }

    // MARK: - Notes

    func loadNotes(projectId: String) async throws -> [ResearchNote] {
        let response: ResearchListResponse<ResearchNote> = try await apiClient.get(
            "/api/research/projects/\(projectId)/notes"
        )
        return response.items
    }

    func createNote(
        projectId: String, content: String, taskId: String? = nil,
        noteType: String = "observation", tags: [String] = []
    ) async throws -> ResearchNote {
        let req = NoteCreateRequest(
            projectId: projectId, taskId: taskId, noteType: noteType, content: content, tags: tags
        )
        // Backend create-note route is POST /api/research/notes (project_id is
        // carried in the body, not the path). See research_notes.py.
        return try await apiClient.post("/api/research/notes", body: req)
    }

    func getNote(id: String) async throws -> ResearchNote {
        try await apiClient.get("/api/research/notes/\(id)")
    }

    func updateNote(
        id: String, content: String? = nil, noteType: String? = nil, tags: [String]? = nil
    ) async throws -> ResearchNote {
        let req = NoteUpdateRequest(content: content, noteType: noteType, tags: tags)
        return try await apiClient.patch("/api/research/notes/\(id)", body: req)
    }

    // MARK: - Sources

    func loadSources(projectId: String) async throws -> [ResearchSource] {
        let response: ResearchListResponse<ResearchSource> = try await apiClient.get(
            "/api/research/projects/\(projectId)/sources"
        )
        return response.items
    }

    func createSource(
        projectId: String, label: String, sourceType: String = "url",
        url: String? = nil, description: String = ""
    ) async throws -> ResearchSource {
        let req = SearchSourceCreateRequest(
            projectId: projectId, sourceType: sourceType, label: label, url: url, description: description
        )
        return try await apiClient.post("/api/research/sources", body: req)
    }

    // MARK: - Web Search

    func webSearch(query: String, projectId: String, maxResults: Int = 10) async throws -> [WebSearchResultItem] {
        let req = WebSearchRequest(query: query, maxResults: maxResults)
        let response: WebSearchResult = try await apiClient.post("/api/research/tools/web-search", body: req)
        return response.results
    }

    // MARK: - Browser Save (download URL → import to library)

    func browserSave(
        url: String, projectId: String, suggestedName: String? = nil, parentFolderId: String? = nil
    ) async throws -> BrowserSaveResponse {
        let req = BrowserSaveRequest(
            url: url, projectId: projectId, suggestedName: suggestedName, parentFolderId: parentFolderId
        )
        return try await apiClient.post("/api/research/tools/browser-save", body: req)
    }
}

// MARK: - Small supporting type for web search results

struct WebSearchResultItem: Codable, Identifiable {
    var title: String
    var url: String
    var snippet: String
    var id: String { url }
}
