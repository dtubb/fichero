import Observation
import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ModelService")

/// ModelService using the generated OpenAPI client.
/// Handles HuggingFace model browsing and selection.
/// Note: Types (HFTaskCategory, HFModelInfo, etc.) are kept in ModelService.swift
@MainActor
@Observable
class ModelService {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - HuggingFace Tasks

    /// List available HuggingFace task categories
    func listHuggingFaceTasks() async throws -> [HFTaskCategory] {
        let response = try await client.api.listHfTasksApiModelsHuggingfaceTasksGet()

        switch response {
        case .ok(let okResponse):
            let tasks = try okResponse.body.json
            return tasks.items.map { convertToHFTaskCategory($0) }
        case .undocumented(let statusCode, _):
            throw ModelServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - HuggingFace Model Search

    /// Search HuggingFace models
    func searchHuggingFaceModels(
        task: String? = nil,
        search: String? = nil,
        sort: HFSortOrder = .downloads,
        limit: Int = 20,
        offset: Int = 0,
        library: String? = nil
    ) async throws -> HFModelSearchResponse {
        let response = try await client.api.searchHfModelsApiModelsHuggingfaceGet(
            query: .init(
                task: task,
                search: search,
                sort: sort.rawValue,
                limit: limit,
                offset: offset,
                library: library
            )
        )

        switch response {
        case .ok(let okResponse):
            let searchResponse = try okResponse.body.json
            return convertToHFModelSearchResponse(searchResponse)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ModelServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ModelServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get details for a specific HuggingFace model
    func getHuggingFaceModel(_ modelId: String) async throws -> HFModelInfo {
        let response = try await client.api.getHfModelApiModelsHuggingfaceModelIdGet(
            path: .init(modelId: modelId)
        )

        switch response {
        case .ok(let okResponse):
            let model = try okResponse.body.json
            return convertToHFModelInfo(model)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ModelServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ModelServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Type Conversions

    private func convertToHFTaskCategory(_ generated: Components.Schemas.HFTaskCategory) -> HFTaskCategory {
        HFTaskCategory(
            id: generated.id,
            label: generated.label
        )
    }

    private func convertToHFModelSearchResponse(_ generated: Components.Schemas.ModelSearchResponse) -> HFModelSearchResponse {
        HFModelSearchResponse(
            models: generated.models.map { convertToHFModelInfo($0) },
            total: generated.total,
            hasMore: generated.hasMore
        )
    }

    private func convertToHFModelInfo(_ generated: Components.Schemas.HFModelInfo) -> HFModelInfo {
        HFModelInfo(
            id: generated.id,
            downloads: generated.downloads,
            likes: generated.likes,
            pipelineTag: generated.pipelineTag,
            libraryName: generated.libraryName,
            createdAt: generated.createdAt,
            tags: generated.tags ?? []
        )
    }
}

// MARK: - Error Types

enum ModelServiceError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from model service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}
