// swiftlint:disable file_length type_body_length
import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ResearchService")

@MainActor
@Observable
final class ResearchService {
    private let client: FicheroClient

    var projects: [ResearchProject] = []
    var selectedProjectId: String?
    var isLoading = false
    var error: String?

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    private enum ServiceError: Error, LocalizedError {
        case unexpectedResponse

        // Shown to users via researchService.error; conform to LocalizedError so
        // it's not the generic "operation couldn't be completed" message (#2500).
        var errorDescription: String? {
            "Unexpected response from the research service."
        }
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = formatter.date(from: dateString) {
                return date
            }

            formatter.formatOptions = [.withInternetDateTime]
            if let date = formatter.date(from: dateString) {
                return date
            }

            let dateFormatter = DateFormatter()
            dateFormatter.locale = Locale(identifier: "en_US_POSIX")
            dateFormatter.timeZone = TimeZone(identifier: "UTC")
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(dateString)"
            )
        }
        return decoder
    }()

    private static let encoder = JSONEncoder()

    private func decodeModel<T: Decodable>(from value: some Encodable, as _: T.Type = T.self) throws -> T {
        let data = try Self.encoder.encode(value)
        return try Self.decoder.decode(T.self, from: data)
    }

    private func decodeModels<T: Decodable>(
        from containers: [OpenAPIValueContainer],
        as _: T.Type = T.self
    ) throws -> [T] {
        try containers.map { container in
            guard let object = container.value else { throw ServiceError.unexpectedResponse }
            let data = try JSONSerialization.data(withJSONObject: object)
            return try Self.decoder.decode(T.self, from: data)
        }
    }

    private func projectStatus(_ status: ResearchProjectStatus?) -> Components.Schemas.FicheroResearchModelsProjectStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    private func planStatus(_ status: ResearchPlanStatus?) -> Components.Schemas.PlanStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    private func taskStatus(_ status: ResearchTaskStatus?) -> Components.Schemas.TaskStatus? {
        status.flatMap { .init(rawValue: $0.rawValueForAPI) }
    }

    private func stepStatus(_ status: ResearchStepStatus?) -> Components.Schemas.StepStatus? {
        status.flatMap { .init(rawValue: $0.rawValue) }
    }

    private func stepTool(_ tool: ResearchStepTool) -> Components.Schemas.StepTool {
        Components.Schemas.StepTool(rawValue: tool.rawValue) ?? .webSearch
    }

    private func researchNoteType(_ noteType: String?) -> Components.Schemas.ResearchNoteType? {
        noteType.flatMap { .init(rawValue: $0) }
    }

    private func researchSourceType(_ sourceType: String) -> Components.Schemas.SearchSourceType {
        Components.Schemas.SearchSourceType(rawValue: sourceType) ?? .url
    }

    // MARK: - Projects

    func loadProjects() async {
        isLoading = true
        error = nil
        do {
            let response = try await client.api.listProjectsApiResearchProjectsGet(
                .init()
            )
            switch response {
            case .ok(let okResponse):
                projects = try decodeModels(from: try okResponse.body.json.items, as: ResearchProject.self)
            case .unprocessableContent, .undocumented:
                throw ServiceError.unexpectedResponse
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load research projects: \(error.localizedDescription)")
        }
        isLoading = false
    }

    func createProject(
        name: String,
        description: String = "",
        folderDestinationId: String? = nil
    ) async throws -> ResearchProject {
        let body = Components.Schemas.FicheroApiRoutesResearchCrudProjectCreateRequest(
            name: name,
            description: description,
            libraryDestinationFolderId: folderDestinationId
        )
        let response = try await client.api.createProjectApiResearchProjectsPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            let project: ResearchProject = try decodeModel(from: try okResponse.body.json)
            projects.append(project)
            return project
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateProject(_ project: ResearchProject) async throws {
        let body = Components.Schemas.ProjectUpdateRequest(
            name: project.name,
            description: project.description,
            status: projectStatus(project.status),
            libraryDestinationFolderId: project.libraryDestinationFolderId
        )
        let response = try await client.api.updateProjectApiResearchProjectsProjectIdPatch(
            .init(
                path: .init(projectId: project.id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            let updated: ResearchProject = try decodeModel(from: try okResponse.body.json)
            if let idx = projects.firstIndex(where: { $0.id == project.id }) {
                projects[idx] = updated
            }
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func deleteProject(id: String) async throws {
        let response = try await client.api.deleteProjectApiResearchProjectsProjectIdDelete(
            .init(
                path: .init(projectId: id),
            )
        )
        switch response {
        case .ok:
            projects.removeAll { $0.id == id }
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Plans

    func loadPlans(projectId: String) async throws -> [ResearchPlan] {
        let response = try await client.api.listPlansApiResearchProjectsProjectIdPlansGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchPlan.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createPlan(projectId: String, name: String, description: String = "") async throws -> ResearchPlan {
        let body = Components.Schemas.PlanCreateRequest(
            projectId: projectId,
            name: name,
            description: description
        )
        let response = try await client.api.createPlanApiResearchPlansPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func getPlan(id: String) async throws -> ResearchPlan {
        let response = try await client.api.getPlanApiResearchPlansPlanIdGet(
            .init(
                path: .init(planId: id),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updatePlan(
        id: String,
        name: String? = nil,
        description: String? = nil,
        status: ResearchPlanStatus? = nil
    ) async throws -> ResearchPlan {
        let body = Components.Schemas.PlanUpdateRequest(
            name: name,
            description: description,
            status: planStatus(status)
        )
        let response = try await client.api.updatePlanApiResearchPlansPlanIdPatch(
            .init(
                path: .init(planId: id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Tasks

    func loadTasks(projectId: String) async throws -> [ResearchTask] {
        let response = try await client.api.listProjectTasksApiResearchProjectsProjectIdTasksGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchTask.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func loadTasks(planId: String) async throws -> [ResearchTask] {
        let response = try await client.api.listTasksApiResearchPlansPlanIdTasksGet(
            .init(
                path: .init(planId: planId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchTask.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createTask(
        planId: String,
        name: String,
        description: String = "",
        priority: Int = 0
    ) async throws -> ResearchTask {
        let body = Components.Schemas.TaskCreateRequest(
            planId: planId,
            name: name,
            description: description,
            priority: priority
        )
        let response = try await client.api.createTaskApiResearchTasksPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func getTask(id: String) async throws -> ResearchTask {
        let response = try await client.api.getTaskApiResearchTasksTaskIdGet(
            .init(
                path: .init(taskId: id),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateTask(
        id: String,
        name: String? = nil,
        description: String? = nil,
        status: ResearchTaskStatus? = nil,
        priority: Int? = nil
    ) async throws -> ResearchTask {
        let body = Components.Schemas.TaskUpdateRequest(
            name: name,
            description: description,
            status: taskStatus(status),
            priority: priority
        )
        let response = try await client.api.updateTaskApiResearchTasksTaskIdPatch(
            .init(
                path: .init(taskId: id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Steps

    func loadSteps(taskId: String) async throws -> [ResearchStep] {
        let response = try await client.api.listStepsApiResearchTasksTaskIdStepsGet(
            .init(
                path: .init(taskId: taskId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchStep.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createStep(
        taskId: String,
        tool: ResearchStepTool,
        label: String,
        description: String = "",
        orderIndex: Int = 0
    ) async throws -> ResearchStep {
        let body = Components.Schemas.StepCreateRequest(
            taskId: taskId,
            tool: stepTool(tool),
            label: label,
            description: description,
            orderIndex: orderIndex
        )
        let response = try await client.api.createStepApiResearchStepsPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateStep(
        id: String,
        label: String? = nil,
        description: String? = nil,
        status: ResearchStepStatus? = nil,
        orderIndex: Int? = nil
    ) async throws -> ResearchStep {
        let body = Components.Schemas.StepUpdateRequest(
            label: label,
            description: description,
            status: stepStatus(status),
            orderIndex: orderIndex
        )
        let response = try await client.api.updateStepApiResearchStepsStepIdPatch(
            .init(
                path: .init(stepId: id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Checklists

    func loadChecklists(projectId: String) async throws -> [ResearchChecklist] {
        let response = try await client.api.listChecklistsApiResearchProjectsProjectIdChecklistsGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchChecklist.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createChecklist(
        projectId: String,
        title: String,
        itemLabels: [String] = [],
        taskId: String? = nil
    ) async throws -> ResearchChecklist {
        let body = Components.Schemas.ChecklistCreateRequest(
            projectId: projectId,
            taskId: taskId,
            title: title,
            items: itemLabels.map { .init(label: $0) }
        )
        let response = try await client.api.createChecklistApiResearchChecklistsPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func toggleChecklistItem(
        checklistId: String,
        itemId: String,
        checked: Bool,
        notes: String = ""
    ) async throws -> ResearchChecklist {
        let body = Components.Schemas.ChecklistItemToggleRequest(checked: checked, notes: notes)
        let response = try await client.api.toggleChecklistItemApiResearchChecklistsChecklistIdItemsItemIdPatch(
            .init(
                path: .init(checklistId: checklistId, itemId: itemId),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Notes

    func loadNotes(projectId: String) async throws -> [ResearchNote] {
        let response = try await client.api.listNotesApiResearchProjectsProjectIdNotesGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchNote.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createNote(
        projectId: String,
        content: String,
        taskId: String? = nil,
        noteType: String = "observation",
        tags: [String] = []
    ) async throws -> ResearchNote {
        let body = Components.Schemas.FicheroApiRoutesResearchNotesNoteCreateRequest(
            projectId: projectId,
            taskId: taskId,
            noteType: researchNoteType(noteType),
            content: content,
            tags: tags
        )
        let response = try await client.api.createNoteApiResearchNotesPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func getNote(id: String) async throws -> ResearchNote {
        let response = try await client.api.getNoteApiResearchNotesNoteIdGet(
            .init(
                path: .init(noteId: id),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func updateNote(
        id: String,
        content: String? = nil,
        noteType: String? = nil,
        tags: [String]? = nil
    ) async throws -> ResearchNote {
        let body = Components.Schemas.NoteUpdateRequest(
            content: content,
            noteType: researchNoteType(noteType),
            tags: tags
        )
        let response = try await client.api.updateNoteApiResearchNotesNoteIdPatch(
            .init(
                path: .init(noteId: id),
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Sources

    func loadSources(projectId: String) async throws -> [ResearchSource] {
        let response = try await client.api.listSearchSourcesApiResearchProjectsProjectIdSourcesGet(
            .init(
                path: .init(projectId: projectId),
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModels(from: try okResponse.body.json.items, as: ResearchSource.self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    func createSource(
        projectId: String,
        label: String,
        sourceType: String = "url",
        url: String? = nil,
        description: String = ""
    ) async throws -> ResearchSource {
        let body = Components.Schemas.SearchSourceCreateRequest(
            projectId: projectId,
            sourceType: researchSourceType(sourceType),
            label: label,
            url: url,
            description: description
        )
        let response = try await client.api.createSearchSourceApiResearchSourcesPost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Web Search

    func webSearch(
        query: String,
        projectId: String,
        maxResults: Int = 10
    ) async throws -> [WebSearchResultItem] {
        _ = projectId
        let body = Components.Schemas.WebSearchRequest(query: query, maxResults: maxResults)
        let response = try await client.api.executeWebSearchApiResearchToolsWebSearchPost(
            .init(body: .json(body))
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json.results, as: [WebSearchResultItem].self)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }

    // MARK: - Browser Save

    func browserSave(
        url: String,
        projectId: String,
        suggestedName: String? = nil,
        parentFolderId: String? = nil
    ) async throws -> BrowserSaveResponse {
        let body = Components.Schemas.BrowserSaveRequest(
            url: url,
            projectId: projectId,
            suggestedName: suggestedName,
            parentFolderId: parentFolderId
        )
        let response = try await client.api.browserSaveApiResearchToolsBrowserSavePost(
            .init(
                body: .json(body)
            )
        )
        switch response {
        case .ok(let okResponse):
            return try decodeModel(from: try okResponse.body.json)
        case .unprocessableContent, .undocumented:
            throw ServiceError.unexpectedResponse
        }
    }
}

struct WebSearchResultItem: Codable, Identifiable {
    var title: String
    var url: String
    var snippet: String
    var id: String { url }
}
// swiftlint:enable file_length type_body_length
