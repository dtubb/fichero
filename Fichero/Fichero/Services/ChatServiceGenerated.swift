import Foundation
import Combine
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ChatService")

/// ChatService using the generated OpenAPI client.
/// This replaces the manual APIClient with type-safe generated calls.
@MainActor
class ChatServiceGenerated: ObservableObject {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Chat

    /// Send a chat message and get a RAG response.
    func chat(
        message: String,
        conversationId: String? = nil,
        documentIds: [String]? = nil,
        includeSources: Bool = true,
        maxSources: Int = 5,
        provider: String? = nil,
        model: String? = nil
    ) async throws -> ChatAPIResponse {
        // Build optional fields using additionalProperties
        var optionalData: [String: Any] = [:]
        if let conversationId = conversationId { optionalData["conversation_id"] = conversationId }
        if let documentIds = documentIds { optionalData["document_ids"] = documentIds }
        if let provider = provider { optionalData["provider"] = provider }
        if let model = model { optionalData["model"] = model }

        let container = try OpenAPIObjectContainer(unvalidatedValue: optionalData)
        let request = Components.Schemas.ChatRequest(
            message: message,
            includeSources: includeSources,
            maxSources: maxSources,
            additionalProperties: container
        )

        let response = try await client.api.chatApiChatPost(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let chatResponse = try okResponse.body.json
            return convertToChatAPIResponse(chatResponse)
        default:
            throw ChatServiceError.unexpectedResponse
        }
    }

    // MARK: - Providers

    /// List available LLM providers.
    func listProviders() async throws -> [LLMProvider] {
        // Providers are app-wide (not per-library), so no library path header needed
        let response = try await client.api.listProvidersApiChatProvidersGet(.init())

        switch response {
        case .ok(let okResponse):
            let providers = try okResponse.body.json
            return providers.map { convertToLLMProvider($0) }
        default:
            throw ChatServiceError.unexpectedResponse
        }
    }

    // MARK: - Text Extraction

    /// Extract text from documents (populates page_content for search/chat).
    func extractText(documentIds: [String]? = nil, force: Bool = false) async throws -> ExtractTextResponse {
        // Build request using additionalProperties since document_ids is optional
        var data: [String: Any] = ["force": force]
        if let documentIds = documentIds { data["document_ids"] = documentIds }

        let container = try OpenAPIObjectContainer(unvalidatedValue: data)
        let request = Components.Schemas.ExtractTextRequest(additionalProperties: container)

        let response = try await client.api.extractTextApiChatExtractTextPost(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let extractResponse = try okResponse.body.json
            return convertToExtractTextResponse(extractResponse)
        default:
            throw ChatServiceError.unexpectedResponse
        }
    }

    // MARK: - Type Conversion

    /// Convert generated ChatResponse to app ChatAPIResponse
    private func convertToChatAPIResponse(_ response: Components.Schemas.ChatResponse) -> ChatAPIResponse {
        ChatAPIResponse(
            message: response.message,
            sources: response.sources.map { source in
                DocumentSourceAPI(
                    documentId: source.documentId,
                    documentName: source.documentName,
                    excerpt: source.excerpt,
                    relevanceScore: source.relevanceScore
                )
            },
            conversationId: response.conversationId,
            modelUsed: response.modelUsed
        )
    }

    /// Convert generated ProviderInfo to app LLMProvider
    private func convertToLLMProvider(_ provider: Components.Schemas.ProviderInfo) -> LLMProvider {
        // Infer vision capability from provider ID based on backend catalog
        // TODO: Regenerate OpenAPI client to include supportsVision from API
        let visionProviders: Set<String> = [
            "apple", "ollama", "lmstudio", "huggingface", "openrouter",
            "openai", "anthropic", "google", "groq", "together",
            "mistral", "dashscope", "xai", "fireworks", "azure", "bedrock"
        ]

        return LLMProvider(
            id: provider.id,
            name: provider.name,
            models: provider.models,
            available: provider.available,
            supportsVision: visionProviders.contains(provider.id)
        )
    }

    /// Convert generated ExtractTextResponse to app ExtractTextResponse
    private func convertToExtractTextResponse(_ response: Components.Schemas.ExtractTextResponse) -> ExtractTextResponse {
        ExtractTextResponse(
            extracted: response.extracted,
            skipped: response.skipped,
            failed: response.failed,
            errors: response.errors
        )
    }
}

// MARK: - Error Types

enum ChatServiceError: Error, LocalizedError {
    case unexpectedResponse
    case invalidData

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .invalidData:
            return "Invalid data received"
        }
    }
}
