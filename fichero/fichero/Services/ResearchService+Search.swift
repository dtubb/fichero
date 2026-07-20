import FicheroAPIClient
import Foundation

extension ResearchService {
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
