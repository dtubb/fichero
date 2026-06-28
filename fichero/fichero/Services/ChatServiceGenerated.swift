import Foundation
import Combine
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ChatService")

/// ChatService using the generated OpenAPI client.
/// This replaces the manual APIClient with type-safe generated calls.
@MainActor
class ChatServiceGenerated: ObservableObject {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Chat

    /// Send a chat message and get a RAG response.  POST /api/chat
    func chat(
        message: String,
        conversationId: String? = nil,
        documentIds: [String]? = nil,
        includeSources: Bool = true,
        maxSources: Int = 5,
        provider: String? = nil,
        model: String? = nil
    ) async throws -> ChatAPIResponse {
        // Use typed fields — conversation_id, document_ids, provider, and
        // model are all declared on ChatRequest. Using additionalProperties
        // for declared fields races the typed-nil encoding (see 31fc4141).
        let request = Components.Schemas.ChatRequest(
            message: message,
            conversationId: conversationId,
            documentIds: documentIds,
            includeSources: includeSources,
            maxSources: maxSources,
            provider: provider,
            model: model
        )

        let response = try await client.api.chatApiChatPost(.init(
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

    /// List available LLM providers.  GET /api/chat/providers
    func listProviders() async throws -> [LLMProvider] {
        // Providers are app-wide (not per-library), so no library path header needed
        let response = try await client.api.listProvidersApiChatProvidersGet(.init())

        switch response {
        case .ok(let okResponse):
            let providers = try okResponse.body.json
            return providers.items.map { convertToLLMProvider($0) }
        default:
            throw ChatServiceError.unexpectedResponse
        }
    }

    // MARK: - Text Extraction

    /// Extract text from documents (populates page_content for search/chat).  POST /api/chat/extract-text
    func extractText(documentIds: [String]? = nil, force: Bool = false) async throws -> ExtractTextResponse {
        // Use typed fields; see 31fc4141.
        let request = Components.Schemas.ExtractTextRequest(
            documentIds: documentIds,
            force: force
        )

        let response = try await client.api.extractTextApiChatExtractTextPost(.init(
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
            modelUsed: response.modelUsed,
            documentCount: response.documentCount ?? 0,
            contextCount: response.contextCount ?? 0,
            kgClaimsUsed: response.kgClaimsUsed ?? 0,
            kgEntitiesUsed: response.kgEntitiesUsed ?? 0
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
