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

    /// Create a plan. Passing a non-empty `term` makes the backend run its
    /// research plan agent and store the result under
    /// `plan.metadata["research_plan"]` (#1729) — the AI assist that shipped
    /// server-side but was unreachable while this wrapper omitted the field.
    ///
    /// `term` is the OpenAPI-typed `PlanCreateRequest.term`, never
    /// `additionalProperties`: a declared field dumped into
    /// `additionalProperties` round-trips on the wire but is dropped by the
    /// Pydantic model, so the request would silently create a blank plan.
    func createPlan(
        projectId: String,
        name: String,
        description: String = "",
        term: String? = nil
    ) async throws -> ResearchPlan {
        let body = Self.planCreateRequest(
            projectId: projectId,
            name: name,
            description: description,
            term: term
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

    /// Request-construction seam for `createPlan` — pure, so the `term`
    /// round-trip is testable without a live client (#1729). A blank/whitespace
    /// term is sent as nil: an empty string would make the backend run the plan
    /// agent on nothing.
    nonisolated static func planCreateRequest(
        projectId: String,
        name: String,
        description: String = "",
        term: String? = nil
    ) -> Components.Schemas.PlanCreateRequest {
        let trimmed = term?.trimmingCharacters(in: .whitespacesAndNewlines)
        return Components.Schemas.PlanCreateRequest(
            projectId: projectId,
            name: name,
            description: description,
            term: (trimmed?.isEmpty == false) ? trimmed : nil
        )
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
