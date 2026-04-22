import Foundation

// MARK: - AI Defaults Model

/// Default AI model configuration per category.
/// Matches the Python AIDefaults Pydantic model.
struct AIDefaults: Codable, Equatable {
    var visionProvider: String = ""
    var visionModel: String = ""
    var textProvider: String = ""
    var textModel: String = ""
    var audioProvider: String = ""
    var audioModel: String = ""
    var videoProvider: String = ""
    var videoModel: String = ""
    var embeddingsProvider: String = ""
    var embeddingsModel: String = ""
    var temperature: String = ""
    var maxTokens: String = ""
    var promptPrefix: String = ""

    enum CodingKeys: String, CodingKey {
        case visionProvider = "vision_provider"
        case visionModel = "vision_model"
        case textProvider = "text_provider"
        case textModel = "text_model"
        case audioProvider = "audio_provider"
        case audioModel = "audio_model"
        case videoProvider = "video_provider"
        case videoModel = "video_model"
        case embeddingsProvider = "embeddings_provider"
        case embeddingsModel = "embeddings_model"
        case temperature
        case maxTokens = "max_tokens"
        case promptPrefix = "prompt_prefix"
    }
}
