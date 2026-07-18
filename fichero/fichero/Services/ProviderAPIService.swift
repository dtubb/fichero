import Observation
import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ProviderAPIService")

/// Service for managing AI providers using generated OpenAPI client
/// Note: Most provider endpoints are global (not library-scoped).
/// Only provider refs endpoints are library-scoped.
// TODO: Refactor ProviderAPIService - extract catalog vs refs into separate services
// Type body is 369 lines, target <350
@MainActor
@Observable
// swiftlint:disable:next type_body_length
class ProviderAPIService {
    private let client: FicheroClient

    /// Initialize with FicheroClient (preferred)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Current library path from the client (used only for refs endpoints)
    private var libraryPath: String {
        client.currentLibraryPath ?? ""
    }

    // MARK: - Catalog (read-only provider info) - Global

    /// List all available provider types from the catalog
    func listCatalog() async throws -> [Components.Schemas.ProviderCatalogResponse] {
        let response = try await client.api.listProviderCatalogApiProvidersCatalogGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get catalog info for a specific provider type
    func getCatalogEntry(_ providerType: String) async throws -> Components.Schemas.ProviderCatalogResponse {
        let response = try await client.api.getCatalogProviderApiProvidersCatalogProviderTypeGet(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - User Provider Configuration - Global

    /// List user's configured providers
    func listProviders() async throws -> [Components.Schemas.ProviderResponse] {
        let response = try await client.api.listProvidersApiProvidersGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Create a new provider configuration
    func createProvider(
        providerType: String,
        name: String? = nil,
        apiBase: String? = nil,
        apiKey: String? = nil
    ) async throws -> Components.Schemas.ProviderResponse {
        let request = Components.Schemas.ProviderCreate(
            providerType: providerType,
            name: name,
            apiBase: apiBase,
            apiKey: apiKey
        )

        let response = try await client.api.createProviderApiProvidersPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get a specific provider configuration
    func getProvider(_ id: String) async throws -> Components.Schemas.ProviderResponse {
        let response = try await client.api.getProviderApiProvidersProviderIdGet(
            path: .init(providerId: id)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Update a provider configuration
    func updateProvider(
        _ id: String,
        name: String? = nil,
        apiBase: String? = nil,
        enabled: Bool? = nil,
        apiKey: String? = nil
    ) async throws -> Components.Schemas.ProviderResponse {
        let request = Components.Schemas.ProviderUpdate(
            name: name,
            apiBase: apiBase,
            enabled: enabled,
            apiKey: apiKey
        )

        let response = try await client.api.updateProviderApiProvidersProviderIdPatch(
            path: .init(providerId: id),
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a provider and its models
    func deleteProvider(_ id: String) async throws {
        let response = try await client.api.deleteProviderApiProvidersProviderIdDelete(
            path: .init(providerId: id)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - API Key Management - Global

    /// Store API key for a provider type in Keychain
    func setAPIKey(providerType: String, apiKey: String) async throws {
        let request = Components.Schemas.APIKeyRequest(apiKey: apiKey)

        let response = try await client.api.setProviderApiKeyApiProvidersProviderTypeApiKeyPost(
            path: .init(providerType: providerType),
            body: .json(request)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete API key for a provider type from Keychain
    func deleteAPIKey(providerType: String) async throws {
        let response = try await client.api.deleteProviderApiKeyApiProvidersProviderTypeApiKeyDelete(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Check if API key exists for a provider type
    func checkAPIKeyStatus(providerType: String) async throws -> APIKeyStatus {
        let response = try await client.api.checkApiKeyStatusApiProvidersProviderTypeApiKeyStatusGet(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok(let okResponse):
            let result = try okResponse.body.json
            return APIKeyStatus(
                providerType: result.providerType,
                hasApiKey: result.hasApiKey,
                isLocal: result.isLocal,
                keychainAvailable: result.keychainAvailable
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Models - Global

    /// List available models for a provider type from LiteLLM registry (returns generated type)
    func listAvailableModelsGenerated(providerType: String) async throws -> [Components.Schemas.ModelResponse] {
        let response = try await client.api.listModelsForProviderApiProvidersModelsProviderTypeGet(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// List available models for a provider type, returning app ModelInfo type (for backward compatibility)
    func listAvailableModels(providerType: String) async throws -> [ModelInfo] {
        let models = try await listAvailableModelsGenerated(providerType: providerType)
        return models.map { convertToModelInfo($0) }
    }

    /// Convert generated ModelResponse to app ModelInfo
    private func convertToModelInfo(_ response: Components.Schemas.ModelResponse) -> ModelInfo {
        ModelInfo(
            modelId: response.modelId,
            fullName: response.fullName,
            description: response.description,
            isRecommended: response.isRecommended ?? false,
            isLocal: response.isLocal ?? false,
            inputCostPerMillion: response.inputCostPerMillion ?? 0,
            outputCostPerMillion: response.outputCostPerMillion ?? 0,
            batchInputCostPerMillion: response.batchInputCostPerMillion,
            batchOutputCostPerMillion: response.batchOutputCostPerMillion,
            cacheReadCostPerMillion: response.cacheReadCostPerMillion,
            maxInputTokens: response.maxInputTokens,
            maxOutputTokens: response.maxOutputTokens,
            mode: response.mode,
            supportsVision: response.supportsVision ?? false,
            supportsFunctionCalling: response.supportsFunctionCalling ?? false,
            supportsAudioInput: response.supportsAudioInput ?? false,
            supportsAudioOutput: response.supportsAudioOutput ?? false,
            supportsPdfInput: response.supportsPdfInput ?? false,
            supportsPromptCaching: response.supportsPromptCaching ?? false,
            supportsReasoning: response.supportsReasoning ?? false,
            supportsWebSearch: response.supportsWebSearch ?? false,
            supportsStreaming: response.supportsStreaming ?? false,
            supportsBatchApi: response.supportsBatchApi ?? false,
            provider: response.provider
        )
    }

    /// List user's configured models for a provider
    func listProviderModels(providerId: String) async throws -> [Components.Schemas.UserModelResponse] {
        let response = try await client.api.listProviderModelsApiProvidersProviderIdModelsGet(
            path: .init(providerId: providerId)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Add a model to a provider
    func addModel(
        providerId: String,
        modelId: String,
        name: String? = nil,
        isDefault: Bool = false
    ) async throws -> Components.Schemas.UserModelResponse {
        let request = Components.Schemas.ModelCreate(
            providerId: providerId,
            modelId: modelId,
            name: name,
            isDefault: isDefault
        )

        let response = try await client.api.addModelToProviderApiProvidersProviderIdModelsPost(
            path: .init(providerId: providerId),
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Remove a model from a provider
    func removeModel(providerId: String, modelId: String) async throws {
        let response = try await client.api.removeModelFromProviderApiProvidersProviderIdModelsModelIdDelete(
            path: .init(providerId: providerId, modelId: modelId)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Connection Testing - Global

    /// Test connection to a provider
    func testConnection(providerType: String) async throws -> Components.Schemas.ConnectionTestResponse {
        let response = try await client.api.testProviderConnectionApiProvidersProviderTypeTestPost(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Provider References (Library-scoped)

    /// List provider references for the current library
    func listProviderRefs() async throws -> [Components.Schemas.ProviderRefResponse] {
        let response = try await client.api.listLibraryProviderRefsApiProvidersRefsGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Add a provider reference to the current library
    func addProviderRef(providerId: String) async throws -> Components.Schemas.ProviderRefResponse {
        let request = Components.Schemas.ProviderRefCreate(providerId: providerId)

        let response = try await client.api.addProviderRefApiProvidersRefsPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Update a provider reference
    func updateProviderRef(
        refId: String,
        enabled: Bool? = nil,
        sortOrder: Int? = nil
    ) async throws -> Components.Schemas.ProviderRefResponse {
        let request = Components.Schemas.ProviderRefUpdate(
            enabled: enabled,
            sortOrder: sortOrder
        )

        let response = try await client.api.updateProviderRefApiProvidersRefsRefIdPatch(
            path: .init(refId: refId),
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a provider reference
    func deleteProviderRef(refId: String) async throws {
        let response = try await client.api.deleteProviderRefApiProvidersRefsRefIdDelete(
            path: .init(refId: refId),
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Type Conversions

    /// Extract API key status from untyped response container
    private func extractAPIKeyStatus(from container: OpenAPIRuntime.OpenAPIValueContainer, providerType: String) -> APIKeyStatus {
        var hasApiKey = false
        var isLocal = false
        var keychainAvailable = true

        if let dict = container.value as? [String: Any] {
            if let hasKey = dict["has_api_key"] as? Bool {
                hasApiKey = hasKey
            }
            if let local = dict["is_local"] as? Bool {
                isLocal = local
            }
            if let keychain = dict["keychain_available"] as? Bool {
                keychainAvailable = keychain
            }
        }

        return APIKeyStatus(
            providerType: providerType,
            hasApiKey: hasApiKey,
            isLocal: isLocal,
            keychainAvailable: keychainAvailable
        )
    }
}

// MARK: - Error Types

enum ProviderAPIServiceError: LocalizedError {
    case validationError(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
