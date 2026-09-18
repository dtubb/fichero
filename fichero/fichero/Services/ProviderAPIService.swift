import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ProviderAPIService")

// Follow-up (#4438): split the global provider catalog from a library's provider
// refs. The header below already names the seam — most endpoints are global,
// only refs are library-scoped — so one type holds two scopes and nothing in
// its signatures says which methods need a library. The 369-line body is the
// symptom; the mixed scope is the defect.

/// Service for managing AI providers using generated OpenAPI client
/// Note: Most provider endpoints are global (not library-scoped).
/// Only provider refs endpoints are library-scoped.
@MainActor
@Observable
class ProviderAPIService {
    private let client: FicheroClient

    /// Initialize with FicheroClient (preferred)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// #4815: local Keychain persistence, injected so a test can fake it —
    /// `ProviderKeyStore` is a plain `enum` of `static func`s hitting the
    /// REAL Keychain directly, so a test must override these rather than
    /// call `setAPIKey`/`deleteAPIKey` unmodified. Defaulted to the real
    /// store for every production caller.
    var storeProviderKey: (String, String) -> Bool = ProviderKeyStore.store
    var removeProviderKey: (String) -> Bool = ProviderKeyStore.remove

    /// Current library path from the client (used only for refs endpoints)
    private var libraryPath: String {
        client.currentLibraryPath ?? ""
    }

    /// Settings mutations change the provider/model set the Run Workflow
    /// context submenus offer (#4189). The engine has no `provider`
    /// change-stream domain and every provider/model/key mutation in the app
    /// funnels through this service, so a successful mutation HERE is the
    /// cache's invalidation signal — the next menu mount refetches once.
    private func invalidateRunWorkflowProviderMenus() {
        WorkflowRunProviderCache.shared.invalidate()
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - API Key Management - Global

    /// The shared HTTP transport both `setAPIKey` (user-facing) and
    /// `supplyAPIKeyToEngine` (engine-only, launch-time) call — #4815's "one
    /// path, not a copy": the difference between the two callers is whether
    /// the app's OWN Keychain is also touched, never the request itself.
    private func postAPIKey(providerType: String, apiKey: String) async throws {
        let request = Components.Schemas.APIKeyRequest(apiKey: apiKey)

        let response = try await client.api.setProviderApiKeyApiProvidersProviderTypeApiKeyPost(
            path: .init(providerType: providerType),
            body: .json(request)
        )

        switch response {
        case .ok:
            invalidateRunWorkflowProviderMenus()
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Store API key for a provider type — the USER-FACING path (Settings).
    /// #4815: ALWAYS pushes to the engine AND persists to the app's own
    /// Keychain, trimmed identically for both — the two stores drifting
    /// apart (Settings never updating the Keychain the launch-time push
    /// reads from) was the whole bug. Never add a flag to skip the Keychain
    /// half here: `supplyAPIKeyToEngine` below is the ONE engine-only path,
    /// kept as a distinct method on purpose — a Bool anyone could pass
    /// `false` to is a standing invitation for this exact regression.
    func setAPIKey(providerType: String, apiKey: String) async throws {
        let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        try await postAPIKey(providerType: providerType, apiKey: trimmed)

        // #4815: the app Keychain is not authoritative for a REMOTE engine —
        // it holds its own keys server-side. Same guard
        // `supplyProviderKeysToEngine` already uses at launch
        // (`EngineLifecycleController+ProviderKeys.swift`).
        guard !EngineConfig.engineProvisioningStrategy().connectsToRemoteHost else { return }
        // The engine already accepted the key — surface a Keychain failure
        // distinctly rather than as a save failure (prefer raise over
        // silent fallback): the key IS live now, it just will not survive
        // the next launch until this is resolved.
        guard storeProviderKey(trimmed, providerType) else {
            throw ProviderAPIServiceError.keyNotPersistedLocally
        }
    }

    /// Delete API key for a provider type — the USER-FACING path (Settings).
    /// #4815: same shape as `setAPIKey` — always engine, then the app's own
    /// Keychain, skipped for a remote engine, a Keychain failure surfaced
    /// distinctly rather than silently.
    func deleteAPIKey(providerType: String) async throws {
        let response = try await client.api.deleteProviderApiKeyApiProvidersProviderTypeApiKeyDelete(
            path: .init(providerType: providerType)
        )

        switch response {
        case .ok:
            invalidateRunWorkflowProviderMenus()
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ProviderAPIServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ProviderAPIServiceError.unexpectedResponse(statusCode)
        }

        guard !EngineConfig.engineProvisioningStrategy().connectsToRemoteHost else { return }
        guard removeProviderKey(providerType) else {
            throw ProviderAPIServiceError.keyNotClearedLocally
        }
    }

    /// #4815/#4534: the ENGINE-ONLY push for the launch-time key supply
    /// (`EngineLifecycleController+ProviderKeys.swift`'s
    /// `supplyProviderKeysToEngine` — its ONLY caller, pinned by a
    /// source-scan guard). It reads a key the app's Keychain ALREADY holds
    /// and hands it to the engine that just (re)started. It must NEVER
    /// write the store it just read — that is the whole reason this is a
    /// separate, distinctly-named method rather than a flag on `setAPIKey`.
    func supplyAPIKeyToEngine(providerType: String, apiKey: String) async throws {
        try await postAPIKey(providerType: providerType, apiKey: apiKey)
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

}

extension ProviderAPIService {
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
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
            invalidateRunWorkflowProviderMenus()
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
    /// #4815: the engine accepted the key, but the app's own Keychain write
    /// failed. Never silently swallowed — the caller must know the key will
    /// not survive the next launch until this is resolved.
    case keyNotPersistedLocally
    /// #4815: the engine removed the key, but the app's own Keychain item
    /// could not be cleared — it may return at the next launch until this
    /// is resolved.
    case keyNotClearedLocally

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        case .keyNotPersistedLocally:
            return "Key saved, but it won't survive the next launch — Keychain error: check Keychain Access or try again."
        case .keyNotClearedLocally:
            return "Key removed, but the saved copy could not be cleared — it may return at the next launch."
        }
    }
}
