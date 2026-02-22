import Foundation
import SwiftUI

// MARK: - Request Models

struct EmptyBody: Codable {}

struct CreateProviderRequest: Encodable {
    let providerType: String
    let name: String?
    let apiBase: String?
    let apiKey: String?

    enum CodingKeys: String, CodingKey {
        case providerType = "provider_type"
        case name
        case apiBase = "api_base"
        case apiKey = "api_key"
    }
}

struct UpdateProviderRequest: Encodable {
    let name: String?
    let apiBase: String?
    let enabled: Bool?
    let apiKey: String?

    enum CodingKeys: String, CodingKey {
        case name
        case apiBase = "api_base"
        case enabled
        case apiKey = "api_key"
    }
}

struct SetAPIKeyRequest: Encodable {
    let apiKey: String

    enum CodingKeys: String, CodingKey {
        case apiKey = "api_key"
    }
}

struct AddModelRequest: Encodable {
    let providerId: String
    let modelId: String
    let name: String?
    let isDefault: Bool

    enum CodingKeys: String, CodingKey {
        case providerId = "provider_id"
        case modelId = "model_id"
        case name
        case isDefault = "is_default"
    }
}

// MARK: - Response Models

struct ProviderCatalogEntry: Codable, Identifiable {
    let type: String
    let name: String
    let description: String
    let apiKeyEnv: String?
    let apiKeyUrl: String?
    let isLocal: Bool
    let isBuiltin: Bool       // True if built into macOS (no config needed)
    let supportsVision: Bool
    let supportsEmbeddings: Bool
    let supportsStreaming: Bool
    let defaultModel: String?
    let hasApiKey: Bool
    // UI metadata (from API - no hardcoded values in frontend)
    let icon: String          // SF Symbol name (fallback)
    let logoAsset: String?    // Bundled image asset name (e.g., "Providers/OpenAI")
    let color: String         // Color name
    let sortOrder: Int        // Display order (lower = first)

    var id: String { type }

    enum CodingKeys: String, CodingKey {
        case type
        case name
        case description
        case apiKeyEnv = "api_key_env"
        case apiKeyUrl = "api_key_url"
        case isLocal = "is_local"
        case isBuiltin = "is_builtin"
        case supportsVision = "supports_vision"
        case supportsEmbeddings = "supports_embeddings"
        case supportsStreaming = "supports_streaming"
        case defaultModel = "default_model"
        case hasApiKey = "has_api_key"
        case icon
        case logoAsset = "logo_asset"
        case color
        case sortOrder = "sort_order"
    }

    /// Convert color name to SwiftUI Color
    var swiftUIColor: Color {
        switch color {
        case "gray": return .gray
        case "blue": return .blue
        case "purple": return .purple
        case "indigo": return .indigo
        case "yellow": return .yellow
        case "green": return .green
        case "orange": return .orange
        case "teal": return .teal
        case "cyan": return .cyan
        case "pink": return .pink
        default: return .accentColor
        }
    }
}

struct ProviderResponse: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let providerType: String
    let apiBase: String?
    let enabled: Bool
    let sortOrder: Int
    let hasApiKey: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case providerType = "provider_type"
        case apiBase = "api_base"
        case enabled
        case sortOrder = "sort_order"
        case hasApiKey = "has_api_key"
        case createdAt = "created_at"
    }
}

struct APIKeyStatus: Codable {
    let providerType: String
    let hasApiKey: Bool
    let isLocal: Bool
    let keychainAvailable: Bool

    enum CodingKeys: String, CodingKey {
        case providerType = "provider_type"
        case hasApiKey = "has_api_key"
        case isLocal = "is_local"
        case keychainAvailable = "keychain_available"
    }
}

struct ModelInfo: Codable, Identifiable, Hashable {
    let modelId: String
    let fullName: String
    let description: String?
    let isRecommended: Bool
    let isLocal: Bool

    // Pricing (per million tokens)
    let inputCostPerMillion: Double
    let outputCostPerMillion: Double
    let batchInputCostPerMillion: Double?
    let batchOutputCostPerMillion: Double?
    let cacheReadCostPerMillion: Double?

    // Context windows
    let maxInputTokens: Int?
    let maxOutputTokens: Int?

    // Mode
    let mode: String?

    // Capabilities
    let supportsVision: Bool
    let supportsFunctionCalling: Bool
    let supportsAudioInput: Bool
    let supportsAudioOutput: Bool
    let supportsPdfInput: Bool
    let supportsPromptCaching: Bool
    let supportsReasoning: Bool
    let supportsWebSearch: Bool
    let supportsStreaming: Bool
    let supportsBatchApi: Bool

    // Provider info
    let provider: String?

    var id: String { modelId }

    enum CodingKeys: String, CodingKey {
        case modelId = "model_id"
        case fullName = "full_name"
        case description
        case isRecommended = "is_recommended"
        case isLocal = "is_local"
        case inputCostPerMillion = "input_cost_per_million"
        case outputCostPerMillion = "output_cost_per_million"
        case batchInputCostPerMillion = "batch_input_cost_per_million"
        case batchOutputCostPerMillion = "batch_output_cost_per_million"
        case cacheReadCostPerMillion = "cache_read_cost_per_million"
        case maxInputTokens = "max_input_tokens"
        case maxOutputTokens = "max_output_tokens"
        case mode
        case supportsVision = "supports_vision"
        case supportsFunctionCalling = "supports_function_calling"
        case supportsAudioInput = "supports_audio_input"
        case supportsAudioOutput = "supports_audio_output"
        case supportsPdfInput = "supports_pdf_input"
        case supportsPromptCaching = "supports_prompt_caching"
        case supportsReasoning = "supports_reasoning"
        case supportsWebSearch = "supports_web_search"
        case supportsStreaming = "supports_streaming"
        case supportsBatchApi = "supports_batch_api"
        case provider
    }

    /// Format cost as price per 1M tokens
    var formattedInputCost: String {
        if isLocal { return "Free" }
        if inputCostPerMillion == 0 { return "Free" }
        return inputCostPerMillion < 0.01 ? "<$0.01" : String(format: "$%.2f", inputCostPerMillion)
    }

    var formattedOutputCost: String {
        if isLocal { return "Free" }
        if outputCostPerMillion == 0 { return "Free" }
        return outputCostPerMillion < 0.01 ? "<$0.01" : String(format: "$%.2f", outputCostPerMillion)
    }

    /// Format context window size
    var formattedContextWindow: String? {
        guard let tokens = maxInputTokens, tokens > 0 else { return nil }
        if tokens >= 1_000_000 {
            return "\(tokens / 1_000_000)M"
        } else if tokens >= 1_000 {
            return "\(tokens / 1_000)K"
        }
        return "\(tokens)"
    }

    /// List of capability badges to show
    var capabilityBadges: [(icon: String, label: String, color: Color)] {
        var badges: [(String, String, Color)] = []
        if supportsVision { badges.append(("eye", "Vision", .purple)) }
        if supportsReasoning { badges.append(("brain", "Reasoning", .pink)) }
        if supportsFunctionCalling { badges.append(("wrench.and.screwdriver", "Tools", .orange)) }
        if supportsAudioInput { badges.append(("mic", "Audio In", .blue)) }
        if supportsAudioOutput { badges.append(("speaker.wave.2", "Audio Out", .blue)) }
        if supportsPdfInput { badges.append(("doc.text", "PDF", .red)) }
        if supportsPromptCaching { badges.append(("memories", "Caching", .green)) }
        if supportsWebSearch { badges.append(("globe", "Web", .teal)) }
        if supportsBatchApi { badges.append(("square.stack.3d.up", "Batch", .indigo)) }
        return badges
    }
}

struct UserModelResponse: Codable, Identifiable {
    let id: String
    let providerId: String
    let name: String
    let modelId: String
    let capabilities: [String]
    let isDefault: Bool
    let enabled: Bool
    let inputCost: Double?
    let outputCost: Double?

    enum CodingKeys: String, CodingKey {
        case id
        case providerId = "provider_id"
        case name
        case modelId = "model_id"
        case capabilities
        case isDefault = "is_default"
        case enabled
        case inputCost = "input_cost"
        case outputCost = "output_cost"
    }
}

struct StatusResponse: Codable {
    let status: String
}

struct ConnectionTestResponse: Codable {
    let success: Bool
    let providerType: String
    let message: String
    let latencyMs: Double?
    let modelTested: String?

    enum CodingKeys: String, CodingKey {
        case success
        case providerType = "provider_type"
        case message
        case latencyMs = "latency_ms"
        case modelTested = "model_tested"
    }
}

// MARK: - Errors

enum ProviderServiceError: LocalizedError {
    case invalidInput(String)

    var errorDescription: String? {
        switch self {
        case .invalidInput(let message):
            return "Invalid input: \(message)"
        }
    }
}
