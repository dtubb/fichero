import Foundation

// MARK: - Provider Types

/// Provider type enum matching Python ProviderType in fichero/models.py
enum ProviderType: String, Codable, CaseIterable, Identifiable {
    // On-device
    case apple
    // Local servers
    case ollama
    case lmstudio
    // Open source
    case huggingface
    // Cloud providers
    case openai
    case anthropic
    case google
    case groq
    case together
    case deepseek
    case mistral
    case cohere
    // Additional LiteLLM providers
    case dashscope
    case xai
    case perplexity
    case fireworks
    case azure
    case bedrock

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .apple: return "Apple Intelligence"
        case .openai: return "OpenAI"
        case .anthropic: return "Anthropic"
        case .huggingface: return "Hugging Face"
        case .google: return "Google AI"
        case .groq: return "Groq"
        case .together: return "Together AI"
        case .deepseek: return "DeepSeek"
        case .mistral: return "Mistral AI"
        case .cohere: return "Cohere"
        case .ollama: return "Ollama"
        case .lmstudio: return "LM Studio"
        case .dashscope: return "DashScope (Qwen)"
        case .xai: return "xAI (Grok)"
        case .perplexity: return "Perplexity"
        case .fireworks: return "Fireworks AI"
        case .azure: return "Azure OpenAI"
        case .bedrock: return "AWS Bedrock"
        }
    }

    var description: String {
        switch self {
        case .apple: return "On-device Apple Vision, Speech"
        case .openai: return "GPT-4o, GPT-4, GPT-3.5, DALL-E, Whisper"
        case .anthropic: return "Claude 4, Claude 3.5, Claude 3"
        case .huggingface: return "Inference API, Inference Endpoints, TGI"
        case .google: return "Gemini 2.0, Gemini 1.5 Pro/Flash"
        case .groq: return "Ultra-fast inference: Llama 3, Mixtral"
        case .together: return "Open source models: Llama, Qwen, Mixtral"
        case .deepseek: return "DeepSeek V3, DeepSeek Coder"
        case .mistral: return "Mistral Large, Codestral, Pixtral"
        case .cohere: return "Command R+, Embed, Rerank"
        case .ollama: return "Run models locally: Llama, Qwen, Mistral"
        case .lmstudio: return "Local GUI for running models"
        case .dashscope: return "Alibaba Cloud: Qwen VL, Qwen Audio"
        case .xai: return "Grok-2, Grok Vision"
        case .perplexity: return "Sonar models with web search"
        case .fireworks: return "Fast inference for open models"
        case .azure: return "Enterprise OpenAI deployment"
        case .bedrock: return "AWS managed models: Claude, Titan"
        }
    }

    var icon: String {
        switch self {
        case .apple: return "apple.logo"
        case .openai: return "brain.head.profile"
        case .anthropic: return "sparkles"
        case .huggingface: return "face.smiling"
        case .google: return "g.circle"
        case .groq: return "bolt.fill"
        case .together: return "square.stack.3d.up"
        case .deepseek: return "magnifyingglass"
        case .mistral: return "wind"
        case .cohere: return "waveform"
        case .ollama: return "desktopcomputer"
        case .lmstudio: return "server.rack"
        case .dashscope: return "cloud.fill"
        case .xai: return "x.circle"
        case .perplexity: return "globe"
        case .fireworks: return "flame"
        case .azure: return "cloud"
        case .bedrock: return "mountain.2"
        }
    }

    var color: String {
        switch self {
        case .apple: return "gray"
        case .openai: return "green"
        case .anthropic: return "purple"
        case .huggingface: return "yellow"
        case .google: return "blue"
        case .groq: return "orange"
        case .together: return "indigo"
        case .deepseek: return "cyan"
        case .mistral: return "teal"
        case .cohere: return "pink"
        case .ollama: return "gray"
        case .lmstudio: return "mint"
        case .dashscope: return "orange"
        case .xai: return "gray"
        case .perplexity: return "blue"
        case .fireworks: return "red"
        case .azure: return "blue"
        case .bedrock: return "orange"
        }
    }

    var isLocal: Bool {
        switch self {
        case .apple, .ollama, .lmstudio: return true
        default: return false
        }
    }

    var signupURL: String? {
        switch self {
        case .apple: return nil
        case .openai: return "https://platform.openai.com/api-keys"
        case .anthropic: return "https://console.anthropic.com/settings/keys"
        case .huggingface: return "https://huggingface.co/settings/tokens"
        case .google: return "https://makersuite.google.com/app/apikey"
        case .groq: return "https://console.groq.com/keys"
        case .together: return "https://api.together.xyz/settings/api-keys"
        case .deepseek: return "https://platform.deepseek.com/api_keys"
        case .mistral: return "https://console.mistral.ai/api-keys"
        case .cohere: return "https://dashboard.cohere.com/api-keys"
        case .ollama: return nil
        case .lmstudio: return nil
        case .dashscope: return "https://dashscope.console.aliyun.com/"
        case .xai: return "https://console.x.ai/"
        case .perplexity: return "https://www.perplexity.ai/settings/api"
        case .fireworks: return "https://fireworks.ai/api-keys"
        case .azure: return "https://portal.azure.com/"
        case .bedrock: return "https://console.aws.amazon.com/bedrock/"
        }
    }

    var defaultBaseURL: String? {
        switch self {
        case .ollama: return "http://localhost:11434"
        case .lmstudio: return "http://localhost:1234"
        default: return nil
        }
    }

    var supportsVision: Bool {
        switch self {
        case .apple, .openai, .anthropic, .huggingface, .google, .groq, .together,
             .mistral, .ollama, .lmstudio, .dashscope, .xai, .fireworks, .azure, .bedrock:
            return true
        case .deepseek, .cohere, .perplexity:
            return false
        }
    }

    var supportsEmbeddings: Bool {
        switch self {
        case .openai, .huggingface, .google, .together, .mistral, .cohere,
             .ollama, .lmstudio, .azure, .bedrock, .fireworks:
            return true
        case .apple, .anthropic, .groq, .deepseek, .dashscope, .xai, .perplexity:
            return false
        }
    }
}

// MARK: - Provider Model

/// Provider configuration matching Python Provider model
struct Provider: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var providerType: ProviderType
    var apiBase: String?
    var enabled: Bool
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case providerType = "provider_type"
        case apiBase = "api_base"
        case enabled
        case createdAt = "created_at"
    }

    init(
        id: String = UUID().uuidString,
        name: String? = nil,
        providerType: ProviderType,
        apiBase: String? = nil,
        enabled: Bool = true,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.name = name ?? providerType.displayName
        self.providerType = providerType
        self.apiBase = apiBase ?? providerType.defaultBaseURL
        self.enabled = enabled
        self.createdAt = createdAt
    }
}

// MARK: - Model

/// AI model configuration matching Python Model
struct AIModel: Identifiable, Codable, Hashable {
    let id: String
    var providerId: String
    var name: String
    var modelId: String
    var capabilities: [String]
    var isDefault: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case providerId = "provider_id"
        case name
        case modelId = "model_id"
        case capabilities
        case isDefault = "is_default"
    }

    init(
        id: String = UUID().uuidString,
        providerId: String,
        name: String,
        modelId: String,
        capabilities: [String] = ["vision", "text"],
        isDefault: Bool = false
    ) {
        self.id = id
        self.providerId = providerId
        self.name = name
        self.modelId = modelId
        self.capabilities = capabilities
        self.isDefault = isDefault
    }
}
