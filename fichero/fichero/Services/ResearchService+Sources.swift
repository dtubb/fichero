import FicheroAPIClient
import Foundation

extension ResearchService {
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
}
