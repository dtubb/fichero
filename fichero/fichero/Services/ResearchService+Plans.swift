import FicheroAPIClient
import Foundation

extension ResearchService {
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
}
