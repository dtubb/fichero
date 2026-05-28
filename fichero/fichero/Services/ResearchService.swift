import Foundation
import OSLog

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ResearchService")

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

    func createProject(name: String, description: String = "", folderDestinationId: String? = nil) async throws -> ResearchProject {
        let req = ProjectCreateRequest(name: name, description: description, libraryDestinationFolderId: folderDestinationId)
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
        let response: ResearchListResponse<ResearchPlan> = try await apiClient.get("/api/research/projects/\(projectId)/plans")
        return response.items
    }

    // MARK: - Tasks

    func loadTasks(projectId: String) async throws -> [ResearchTask] {
        let response: ResearchListResponse<ResearchTask> = try await apiClient.get("/api/research/projects/\(projectId)/tasks")
        return response.items
    }

    // MARK: - Notes

    func loadNotes(projectId: String) async throws -> [ResearchNote] {
        let response: ResearchListResponse<ResearchNote> = try await apiClient.get("/api/research/projects/\(projectId)/notes")
        return response.items
    }

    func createNote(
        projectId: String, content: String, taskId: String? = nil,
        noteType: String = "observation", tags: [String] = []
    ) async throws -> ResearchNote {
        let req = NoteCreateRequest(projectId: projectId, taskId: taskId, noteType: noteType, content: content, tags: tags)
        return try await apiClient.post("/api/research/projects/\(projectId)/notes", body: req)
    }

    // MARK: - Sources

    func loadSources(projectId: String) async throws -> [ResearchSource] {
        let response: ResearchListResponse<ResearchSource> = try await apiClient.get("/api/research/projects/\(projectId)/sources")
        return response.items
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
        let req = BrowserSaveRequest(url: url, projectId: projectId, suggestedName: suggestedName, parentFolderId: parentFolderId)
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
