import FicheroAPIClient
import Foundation

extension ResearchService {
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
}
