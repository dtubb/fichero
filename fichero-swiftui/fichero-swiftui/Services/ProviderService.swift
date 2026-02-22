import Foundation
import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ProviderService")

/// Service for managing AI providers via the backend API.
/// API keys are stored in macOS Keychain via the Python backend.
@MainActor
class ProviderService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Input Validation

    /// Validate an identifier to prevent path traversal attacks
    private func validateIdentifier(_ identifier: String, type: String) throws {
        // Reject identifiers containing path traversal sequences
        let invalidPatterns = ["..", "/", "\\", "%2e", "%2f", "%5c"]
        for pattern in invalidPatterns {
            if identifier.lowercased().contains(pattern) {
                logger.error("Invalid \(type) detected: contains forbidden pattern")
                throw ProviderServiceError.invalidInput("Invalid \(type) format")
            }
        }
        // Allow alphanumeric, hyphen, underscore, and dot (for provider types like "openai")
        let allowedCharacters = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        if identifier.unicodeScalars.contains(where: { !allowedCharacters.contains($0) }) {
            logger.error("Invalid \(type) detected: contains invalid characters")
            throw ProviderServiceError.invalidInput("Invalid \(type) format")
        }
    }

    // MARK: - Catalog (read-only provider info)

    /// List all available provider types from the catalog.
    func listCatalog() async throws -> [ProviderCatalogEntry] {
        try await api.get("/providers/catalog")
    }

    /// Get catalog info for a specific provider type.
    func getCatalogEntry(_ providerType: String) async throws -> ProviderCatalogEntry {
        try validateIdentifier(providerType, type: "provider type")
        return try await api.get("/providers/catalog/\(providerType)")
    }

    // MARK: - User Provider Configuration

    /// List user's configured providers.
    func listProviders() async throws -> [ProviderResponse] {
        try await api.get("/providers")
    }

    /// Create a new provider configuration.
    /// API key is stored in Keychain by the backend.
    func createProvider(
        providerType: String,
        name: String? = nil,
        apiBase: String? = nil,
        apiKey: String? = nil
    ) async throws -> ProviderResponse {
        try validateIdentifier(providerType, type: "provider type")
        let request = CreateProviderRequest(
            providerType: providerType,
            name: name,
            apiBase: apiBase,
            apiKey: apiKey
        )
        return try await api.post("/providers", body: request)
    }

    /// Get a specific provider configuration.
    func getProvider(_ id: String) async throws -> ProviderResponse {
        try validateIdentifier(id, type: "provider ID")
        return try await api.get("/providers/\(id)")
    }

    /// Update a provider configuration.
    func updateProvider(
        _ id: String,
        name: String? = nil,
        apiBase: String? = nil,
        enabled: Bool? = nil,
        apiKey: String? = nil
    ) async throws -> ProviderResponse {
        try validateIdentifier(id, type: "provider ID")
        let request = UpdateProviderRequest(
            name: name,
            apiBase: apiBase,
            enabled: enabled,
            apiKey: apiKey
        )
        return try await api.patch("/providers/\(id)", body: request)
    }

    /// Delete a provider and its models.
    func deleteProvider(_ id: String) async throws {
        try validateIdentifier(id, type: "provider ID")
        try await api.delete("/providers/\(id)")
    }

    // MARK: - API Key Management

    /// Store API key for a provider type in Keychain.
    func setAPIKey(providerType: String, apiKey: String) async throws {
        try validateIdentifier(providerType, type: "provider type")
        let request = SetAPIKeyRequest(apiKey: apiKey)
        let _: StatusResponse = try await api.post("/providers/\(providerType)/api-key", body: request)
    }

    /// Delete API key for a provider type from Keychain.
    func deleteAPIKey(providerType: String) async throws {
        try validateIdentifier(providerType, type: "provider type")
        try await api.delete("/providers/\(providerType)/api-key")
    }

    /// Check if API key exists for a provider type.
    func checkAPIKeyStatus(providerType: String) async throws -> APIKeyStatus {
        try validateIdentifier(providerType, type: "provider type")
        return try await api.get("/providers/\(providerType)/api-key/status")
    }

    // MARK: - Models

    /// List available models for a provider type from LiteLLM registry.
    func listAvailableModels(providerType: String) async throws -> [ModelInfo] {
        try validateIdentifier(providerType, type: "provider type")
        return try await api.get("/providers/models/\(providerType)")
    }

    /// List user's configured models for a provider.
    func listProviderModels(providerId: String) async throws -> [UserModelResponse] {
        try validateIdentifier(providerId, type: "provider ID")
        return try await api.get("/providers/\(providerId)/models")
    }

    /// Add a model to a provider.
    func addModel(
        providerId: String,
        modelId: String,
        name: String? = nil,
        isDefault: Bool = false
    ) async throws -> UserModelResponse {
        try validateIdentifier(providerId, type: "provider ID")
        try validateIdentifier(modelId, type: "model ID")
        let request = AddModelRequest(
            providerId: providerId,
            modelId: modelId,
            name: name,
            isDefault: isDefault
        )
        return try await api.post("/providers/\(providerId)/models", body: request)
    }

    /// Remove a model from a provider.
    func removeModel(providerId: String, modelId: String) async throws {
        try validateIdentifier(providerId, type: "provider ID")
        try validateIdentifier(modelId, type: "model ID")
        try await api.delete("/providers/\(providerId)/models/\(modelId)")
    }

    // MARK: - Connection Testing

    /// Test connection to a provider.
    func testConnection(providerType: String) async throws -> ConnectionTestResponse {
        try validateIdentifier(providerType, type: "provider type")
        return try await api.post("/providers/\(providerType)/test", body: EmptyBody())
    }
}
