import FicheroAPIClient
import Foundation

extension ResearchService {
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
}
